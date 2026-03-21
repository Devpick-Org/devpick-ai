from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends

from app.api.deps import verify_internal_key
from app.core.exceptions import AIBadRequestError
from app.rag.retriever import RAGRetriever
from app.repositories.answer_repository import AnswerRepository
from app.repositories.summary_repository import SummaryRepository
from app.repositories.vector_repository import VectorRepository
from app.schemas.answer import AnswerRequest, AnswerResponse, RelatedContent
from app.schemas.refine import RefineRequest, RefineResponse
from app.schemas.similar_question import SimilarQuestionRequest, SimilarQuestionResponse
from app.schemas.summary import SummaryRequest, SummaryResponse
from app.services.answer_service import AnswerService
from app.services.embedding_service import EmbeddingOrchestrator
from app.services.preprocess_service import PreprocessService
from app.services.question_embedding_service import QuestionEmbeddingOrchestrator
from app.services.refine_service import RefineService
from app.services.similar_question_service import SimilarQuestionService
from app.services.summary_service import SummaryService

load_dotenv()
_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_MONGO_URI = os.getenv("MONGO_URI", "")
_MONGO_DB = os.getenv("MONGO_DB", "devpick")
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

logger = logging.getLogger(__name__)

_LEVEL_MAP: dict[str, str] = {
    "BEGINNER": "junior",
    "JUNIOR": "junior",
    "MIDDLE": "mid",
    "SENIOR": "senior",
    "junior": "junior",
    "mid": "mid",
    "senior": "senior",
}

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/health", dependencies=[Depends(verify_internal_key)])
def internal_health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/summary",
    response_model=SummaryResponse,
    dependencies=[Depends(verify_internal_key)],
)
def create_summary(body: SummaryRequest) -> SummaryResponse:
    """콘텐츠 AI 요약 생성.

    에러는 전역 핸들러(AIServiceError)가 처리한다.
    라우터는 입력 검증 + 서비스 호출만 담당한다.
    """
    level = _LEVEL_MAP.get(body.level)
    if level is None:
        raise AIBadRequestError(
            f"지원하지 않는 레벨: {body.level!r}. JUNIOR/MIDDLE/SENIOR 또는 junior/mid/senior 사용"
        )

    try:
        preprocessed = PreprocessService().preprocess(body.text)
    except ValueError as exc:
        raise AIBadRequestError(str(exc)) from exc

    result = SummaryService(api_key=_ANTHROPIC_API_KEY).summarize(
        content_id=body.content_id,
        level=level,
        text=preprocessed,
        thumbnail_url=body.thumbnail_url,
    )

    # MongoDB 저장 (fire-and-forget: 실패해도 응답은 반환)
    if _MONGO_URI:
        try:
            SummaryRepository(mongo_uri=_MONGO_URI, db_name=_MONGO_DB).save(result)
        except Exception:
            logger.exception("Failed to save summary to MongoDB")

    # 임베딩 + RAG 저장 (fire-and-forget: 실패해도 응답은 반환)
    if _OPENAI_API_KEY and _MONGO_URI:
        try:
            EmbeddingOrchestrator(
                openai_api_key=_OPENAI_API_KEY,
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

    return RefineService(api_key=_ANTHROPIC_API_KEY).refine(
        title=body.title,
        content=body.content,
        context_chunks=context_chunks,
    )


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
    if _OPENAI_API_KEY:
        try:
            query = f"{body.refined_title} {body.refined_content}"
            results = RAGRetriever(openai_api_key=_OPENAI_API_KEY).search(
                query, top_k=5
            )
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
    result, references = AnswerService(api_key=_ANTHROPIC_API_KEY).answer(
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
    if body.question_id and _OPENAI_API_KEY and _MONGO_URI:
        try:
            question_text = f"{body.refined_title}\n{body.refined_content}"
            QuestionEmbeddingOrchestrator(
                openai_api_key=_OPENAI_API_KEY,
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
    if not _OPENAI_API_KEY:
        raise AIBadRequestError("OpenAI API 키가 설정되지 않았습니다")

    results = SimilarQuestionService(
        openai_api_key=_OPENAI_API_KEY,
    ).search(
        text=body.text,
        top_k=body.top_k,
        exclude_question_id=body.question_id,
    )

    return SimilarQuestionResponse(results=results, total=len(results))
