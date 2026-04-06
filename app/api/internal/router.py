from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Depends

from app.api.deps import verify_internal_key
from app.core.exceptions import AIBadRequestError
from app.rag.retriever import RAGRetriever
from app.repositories.answer_repository import AnswerRepository
from app.repositories.event_repository import EventRepository
from app.repositories.insight_repository import InsightRepository
from app.repositories.question_vector_repository import QuestionVectorRepository
from app.repositories.summary_repository import SummaryRepository
from app.repositories.vector_repository import VectorRepository
from app.schemas.answer import AnswerRequest, AnswerResponse, RelatedContent
from app.schemas.event import EventType
from app.schemas.insight import InsightRequest, InsightResponse
from app.schemas.refine import RefineRequest, RefineResponse
from app.schemas.similar_question import SimilarQuestionRequest, SimilarQuestionResponse
from app.schemas.summary import (
    AllLevelsSummaryRequest,
    AllLevelsSummaryResponse,
)
from app.services.all_levels_summary_service import AllLevelsSummaryService
from app.services.answer_service import AnswerService
from app.services.embedding_service import EmbeddingOrchestrator
from app.services.insight_service import InsightService
from app.services.preprocess_service import PreprocessService
from app.services.question_embedding_service import QuestionEmbeddingOrchestrator
from app.services.refine_service import RefineService
from app.services.similar_question_service import SimilarQuestionService

load_dotenv()
_AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-2")
_BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "anthropic.claude-sonnet-4-5")
_MONGO_URI = os.getenv("MONGO_URI", "")
_MONGO_DB = os.getenv("MONGO_DB", "devpick")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/health", dependencies=[Depends(verify_internal_key)])
def internal_health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/summaries",
    response_model=AllLevelsSummaryResponse,
    dependencies=[Depends(verify_internal_key)],
)
def create_all_levels_summary(
    body: AllLevelsSummaryRequest,
) -> AllLevelsSummaryResponse:
    """콘텐츠 4레벨 동시 AI 요약 생성 (DP-300).

    Backend가 콘텐츠 저장 직후 호출한다.
    에러는 전역 핸들러(AIServiceError)가 처리한다.
    """
    try:
        preprocessed = PreprocessService().preprocess(body.text)
    except ValueError as exc:
        raise AIBadRequestError(str(exc)) from exc

    result = AllLevelsSummaryService(aws_region=_AWS_REGION, model=_BEDROCK_MODEL).summarize_all(
        content_id=body.content_id,
        text=preprocessed,
        thumbnail_url=body.thumbnail_url,
    )

    # MongoDB 저장 (fire-and-forget)
    if _MONGO_URI:
        try:
            SummaryRepository(mongo_uri=_MONGO_URI, db_name=_MONGO_DB).save_all_levels(
                content_id=body.content_id,
                response=result,
            )
        except Exception:
            logger.exception("Failed to save all-levels summary to MongoDB")

    # 임베딩 + RAG 저장 (fire-and-forget)
    if _MONGO_URI:
        try:
            EmbeddingOrchestrator(
                aws_region=_AWS_REGION,
                mongo_uri=_MONGO_URI,
                mongo_db=_MONGO_DB,
            ).embed_and_store(
                content_id=body.content_id,
                preprocessed_text=preprocessed,
                summary=result,
            )
        except Exception:
            logger.exception("Failed to embed content for RAG")

    return result


@router.post(
    "/refine",
    response_model=RefineResponse,
    dependencies=[Depends(verify_internal_key)],
)
def create_refine(body: RefineRequest) -> RefineResponse:
    """질문 AI 개선 생성 (DP-231).

    에러는 전역 핸들러(AIServiceError)가 처리한다.
    라우터는 컨텍스트 조회 + 서비스 호출만 담당한다.
    """
    # content_id가 있으면 MongoDB에서 해당 아티클 청크 조회 (fire-and-forget)
    context_chunks: list[str] | None = None
    if body.content_id and _MONGO_URI:
        try:
            docs = VectorRepository(
                mongo_uri=_MONGO_URI, db_name=_MONGO_DB
            ).find_by_content_id(body.content_id)
            if docs:
                context_chunks = [doc["text"] for doc in docs]
        except Exception:
            logger.exception("Failed to fetch context chunks from MongoDB")

    result = RefineService(aws_region=_AWS_REGION, model=_BEDROCK_MODEL).refine(
        title=body.title,
        content=body.content,
        context_chunks=context_chunks,
    )

    # 이벤트 로그 저장 (fire-and-forget, DP-252)
    if body.user_id and _MONGO_URI:
        try:
            EventRepository(mongo_uri=_MONGO_URI, db_name=_MONGO_DB).save_event(
                user_id=body.user_id,
                event_type=EventType.QUESTION_REFINED,
                content_id=body.content_id,
            )
        except Exception:
            logger.exception("Failed to save event log")

    return result


@router.post(
    "/answer",
    response_model=AnswerResponse,
    dependencies=[Depends(verify_internal_key)],
)
def create_answer(body: AnswerRequest) -> AnswerResponse:
    """질문 AI 1차 답변 생성 (DP-234).

    에러는 전역 핸들러(AIServiceError)가 처리한다.
    라우터는 컨텍스트 조회 + 서비스 호출 + related_contents 주입을 담당한다.
    """
    # Step 1. content_id 있으면 해당 아티클 청크 조회
    article_chunks: list[str] | None = None
    if body.content_id and _MONGO_URI:
        try:
            docs = VectorRepository(
                mongo_uri=_MONGO_URI, db_name=_MONGO_DB
            ).find_by_content_id(body.content_id)
            if docs:
                article_chunks = [doc["text"] for doc in docs]
        except Exception:
            logger.exception("Failed to fetch article chunks from MongoDB")

    # Step 2. RAG 유사 문서 검색 (항상 시도)
    rag_chunks: list[str] | None = None
    try:
        query = f"{body.refined_title} {body.refined_content}"
        results = RAGRetriever(aws_region=_AWS_REGION).search(query, top_k=5)
        filtered = [
            (doc, score)
            for doc, score in results
            if doc.metadata.content_id != body.content_id
        ]
        if filtered:
            rag_chunks = [
                f"[출처: {doc.metadata.content_id}]\n{doc.text}"
                for doc, _ in filtered
            ]
    except Exception:
        logger.exception("Failed to perform RAG search")

    # Step 3. 답변 생성
    result, references = AnswerService(aws_region=_AWS_REGION, model=_BEDROCK_MODEL).answer(
        refined_title=body.refined_title,
        refined_content=body.refined_content,
        original_title=body.original_title,
        original_content=body.original_content,
        suggested_tags=body.suggested_tags,
        article_chunks=article_chunks,
        rag_chunks=rag_chunks,
    )

    # Step 4. references 기반 related_contents 주입
    if references and _MONGO_URI:
        try:
            summaries = SummaryRepository(
                mongo_uri=_MONGO_URI, db_name=_MONGO_DB
            ).find_by_content_ids(references)
            result.related_contents = [
                RelatedContent(
                    content_id=s["content_id"],
                    one_line_summary=s["one_line_summary"],
                )
                for s in summaries
            ]
        except Exception:
            logger.exception("Failed to fetch related contents from MongoDB")

    # Step 5. 답변 MongoDB 저장 (fire-and-forget)
    if _MONGO_URI:
        try:
            AnswerRepository(mongo_uri=_MONGO_URI, db_name=_MONGO_DB).save(
                result,
                question_id=body.question_id,
                content_id=body.content_id,
            )
        except Exception:
            logger.exception("Failed to save answer to MongoDB")

    # Step 6. 질문 임베딩 저장 (fire-and-forget)
    if body.question_id and _MONGO_URI:
        try:
            question_text = f"{body.refined_title}\n{body.refined_content}"
            QuestionEmbeddingOrchestrator(
                aws_region=_AWS_REGION,
                mongo_uri=_MONGO_URI,
                mongo_db=_MONGO_DB,
            ).embed_and_store(
                question_id=body.question_id,
                text=question_text,
                suggested_tags=body.suggested_tags,
                content_id=body.content_id,
            )
        except Exception:
            logger.exception("Failed to embed question for RAG")

    # Step 7. 이벤트 로그 저장 (fire-and-forget, DP-252)
    if body.user_id and _MONGO_URI:
        try:
            EventRepository(mongo_uri=_MONGO_URI, db_name=_MONGO_DB).save_event(
                user_id=body.user_id,
                event_type=EventType.ANSWER_GENERATED,
                content_id=body.content_id,
                question_id=body.question_id,
            )
        except Exception:
            logger.exception("Failed to save event log")

    return result


@router.post(
    "/similar-questions",
    response_model=SimilarQuestionResponse,
    dependencies=[Depends(verify_internal_key)],
)
def search_similar_questions(body: SimilarQuestionRequest) -> SimilarQuestionResponse:
    """유사 질문 검색 (DP-235).

    FAISS questions 인덱스에서 유사한 질문을 검색한다.
    에러는 전역 핸들러(AIServiceError)가 처리한다.
    """
    results = SimilarQuestionService(
        aws_region=_AWS_REGION,
    ).search(
        text=body.text,
        top_k=body.top_k,
        exclude_question_id=body.question_id,
    )

    # 이벤트 로그 저장 (fire-and-forget, DP-252)
    if body.user_id and _MONGO_URI:
        try:
            EventRepository(mongo_uri=_MONGO_URI, db_name=_MONGO_DB).save_event(
                user_id=body.user_id,
                event_type=EventType.SIMILAR_QUESTIONS_SEARCHED,
                question_id=body.question_id,
            )
        except Exception:
            logger.exception("Failed to save event log")

    return SimilarQuestionResponse(results=results, total=len(results))


@router.post(
    "/report",
    response_model=InsightResponse,
    dependencies=[Depends(verify_internal_key)],
)
def create_insight(body: InsightRequest) -> InsightResponse:
    """주간 리포트 AI 인사이트 생성 (DP-259).

    백엔드가 주간 리포트 생성 후 호출한다.
    에러는 전역 핸들러(AIServiceError)가 처리한다.
    MongoDB 저장 실패는 무시하고 InsightResponse를 반환한다.
    """
    # Step 1. 주간 AI 이벤트 카운트 (event_logs 조회)
    ai_events: dict = {"refine": 0, "answer": 0, "similar": 0}
    if _MONGO_URI:
        try:
            week_start_dt = datetime.fromisoformat(body.week_start).replace(
                tzinfo=timezone.utc
            )
            week_end_dt = datetime.fromisoformat(body.week_end).replace(
                tzinfo=timezone.utc
            ) + timedelta(days=1)
            events = EventRepository(
                mongo_uri=_MONGO_URI, db_name=_MONGO_DB
            ).find_by_user(
                user_id=body.user_id,
                start=week_start_dt,
                end=week_end_dt,
            )
            ai_events = {
                "refine": sum(
                    1
                    for e in events
                    if e["event_type"] == EventType.QUESTION_REFINED.value
                ),
                "answer": sum(
                    1
                    for e in events
                    if e["event_type"] == EventType.ANSWER_GENERATED.value
                ),
                "similar": sum(
                    1
                    for e in events
                    if e["event_type"] == EventType.SIMILAR_QUESTIONS_SEARCHED.value
                ),
            }
        except Exception:
            logger.exception("Failed to fetch AI event counts from MongoDB")

    # Step 2. 읽은 글 / 스크랩한 글 one_line_summary 조회
    read_summaries: list[dict] = []
    scrapped_summaries: list[dict] = []
    if _MONGO_URI:
        try:
            repo = SummaryRepository(mongo_uri=_MONGO_URI, db_name=_MONGO_DB)
            if body.activities.read_content_ids:
                read_summaries = repo.find_by_content_ids(
                    body.activities.read_content_ids
                )
            if body.activities.scrapped_content_ids:
                scrapped_summaries = repo.find_by_content_ids(
                    body.activities.scrapped_content_ids
                )
        except Exception:
            logger.exception("Failed to fetch article summaries from MongoDB")

    # Step 3. 작성한 질문 텍스트 조회
    question_texts: list[str] = []
    if _MONGO_URI and body.activities.question_ids:
        try:
            question_texts = QuestionVectorRepository(
                mongo_uri=_MONGO_URI, db_name=_MONGO_DB
            ).find_texts_by_ids(body.activities.question_ids)
        except Exception:
            logger.exception("Failed to fetch question texts from MongoDB")

    # Step 4. 인사이트 생성
    result = InsightService(aws_region=_AWS_REGION, model=_BEDROCK_MODEL).generate(
        activities=body.activities,
        ai_events=ai_events,
        read_summaries=read_summaries,
        scrapped_summaries=scrapped_summaries,
        question_texts=question_texts,
        week_start=body.week_start,
        week_end=body.week_end,
    )
    result.report_id = body.report_id

    # Step 5. 인사이트 MongoDB 저장 (fire-and-forget)
    if _MONGO_URI:
        try:
            InsightRepository(mongo_uri=_MONGO_URI, db_name=_MONGO_DB).save(
                report_id=body.report_id,
                user_id=body.user_id,
                response=result,
            )
        except Exception:
            logger.exception("Failed to save insight to MongoDB")

    # Step 6. 이벤트 로그 저장 (fire-and-forget)
    if _MONGO_URI:
        try:
            EventRepository(mongo_uri=_MONGO_URI, db_name=_MONGO_DB).save_event(
                user_id=body.user_id,
                event_type=EventType.INSIGHT_GENERATED,
            )
        except Exception:
            logger.exception("Failed to save insight event log")

    return result
