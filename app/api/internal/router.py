from __future__ import annotations

import logging
import os
from datetime import datetime, time, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import verify_internal_key
from app.core.exceptions import AIBadRequestError
from app.rag.retriever import RAGRetriever
from app.repositories.answer_repository import AnswerRepository
from app.repositories.event_repository import EventRepository
from app.repositories.insight_repository import InsightRepository
from app.repositories.user_repository import UserRepository
from app.repositories.question_vector_repository import QuestionVectorRepository
from app.repositories.quiz_repository import QuizRepository
from app.repositories.summary_repository import SummaryRepository
from app.repositories.vector_repository import VectorRepository
from app.repositories.content_repository import ContentRepository
from app.repositories.trend_repository import TrendSnapshotRepository
from app.schemas.answer import AnswerRequest, AnswerResponse, RelatedContent
from app.schemas.event import EventType
from app.schemas.insight import InsightRequest, InsightResponse
from app.schemas.quiz import AllLevelsQuizResponse, QuizRequest
from app.schemas.refine import RefineRequest, RefineResponse
from app.schemas.similar_content import SimilarContentRequest, SimilarContentResponse
from app.schemas.similar_question import SimilarQuestionRequest, SimilarQuestionResponse
from app.schemas.summary import (
    AllLevelsSummaryRequest,
    AllLevelsSummaryResponse,
)
from app.schemas.job_ai import (
    InterviewQaRequest,
    MockInterviewFinalizeRequest,
    MockInterviewFinalizeResponse,
    MockInterviewPlan,
    MockInterviewPlanRequest,
    MockInterviewTurnRequest,
    MockInterviewTurnResponse,
    ParseJdRequest,
    ParseJdResponse,
    ResumeEnrichRequest,
    ResumeParseRequest,
    SkillGapRequest,
    SkillGapResponse,
)
from app.schemas.trend import TrendGenerateRequest, TrendResponse
from app.services.all_levels_summary_service import AllLevelsSummaryService
from app.services.answer_service import AnswerService
from app.services.embedding_service import EmbeddingOrchestrator
from app.services.quiz_service import QuizService
from app.services.insight_service import InsightService
from app.services.preprocess_service import PreprocessService
from app.services.question_cleanup_service import cleanup_question_documents
from app.services.question_embedding_service import QuestionEmbeddingOrchestrator
from app.services.refine_service import RefineService
from app.services.similar_content_service import SimilarContentService
from app.services.similar_question_service import SimilarQuestionService
from app.services.job_ai_service import JobAiService
from app.services.trend.orchestrator import (
    TrendOrchestrator,
    compute_period,
    compute_period_end,
)

load_dotenv()
_AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-2")
_BEDROCK_REGION = os.getenv("BEDROCK_REGION", "ap-northeast-2")
_DEFAULT_SONNET = "global.anthropic.claude-sonnet-4-6"
_BEDROCK_MODEL_SONNET = os.getenv("BEDROCK_MODEL_SONNET") or _DEFAULT_SONNET
_BEDROCK_MODEL_HAIKU = os.getenv(
    "BEDROCK_MODEL_HAIKU",
    "global.anthropic.claude-haiku-4-5-20251001-v1:0",
)
# 채용(Job AI): parse-jd·interview-qa·skill-gap 공통 — 트렌드·인사이트와 동일 Sonnet 4.6 기본값
_DEFAULT_JOB_AI_MODEL = "global.anthropic.claude-sonnet-4-6"
_BEDROCK_MODEL_JOB_AI = os.getenv("BEDROCK_MODEL_JOB_AI") or _DEFAULT_JOB_AI_MODEL
_DATABASE_URL = os.getenv("DATABASE_URL")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/health", dependencies=[Depends(verify_internal_key)])
def internal_health() -> dict[str, str]:
    return {"status": "ok"}


@router.delete(
    "/questions/{question_id}",
    status_code=204,
    dependencies=[Depends(verify_internal_key)],
)
def delete_question_documents(question_id: str) -> Response:
    """백엔드 posts 삭제 후 호출 — ai_answers·rag_questions·FAISS 질문 인덱스 정리.

    존재하지 않는 question_id여도 204(멱등).
    """
    cleanup_question_documents(question_id, _AWS_REGION)
    return Response(status_code=204)


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

    result = AllLevelsSummaryService(
        aws_region=_BEDROCK_REGION, model=_BEDROCK_MODEL_HAIKU
    ).summarize_all(
        content_id=body.content_id,
        text=preprocessed,
        thumbnail_url=body.thumbnail_url,
        title=body.title,
    )

    # DynamoDB 저장 (fire-and-forget)
    try:
        SummaryRepository(aws_region=_AWS_REGION).save_all_levels(
            content_id=body.content_id,
            response=result,
        )
    except Exception:
        logger.exception("Failed to save all-levels summary to DynamoDB")

    # 임베딩 + RAG 저장 (fire-and-forget)
    try:
        EmbeddingOrchestrator(aws_region=_AWS_REGION).embed_and_store(
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
    # content_id가 있으면 DynamoDB에서 해당 아티클 청크 조회
    context_chunks: list[str] | None = None
    if body.content_id:
        try:
            docs = VectorRepository(aws_region=_AWS_REGION).find_by_content_id(
                body.content_id
            )
            if docs:
                context_chunks = [doc["text"] for doc in docs]
        except Exception:
            logger.exception("Failed to fetch context chunks from DynamoDB")

    result = RefineService(
        aws_region=_BEDROCK_REGION, model=_BEDROCK_MODEL_SONNET
    ).refine(
        title=body.title,
        content=body.content,
        context_chunks=context_chunks,
    )

    # 이벤트 로그 저장 (fire-and-forget, DP-252)
    if body.user_id:
        try:
            EventRepository(aws_region=_AWS_REGION).save_event(
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
    if body.content_id:
        try:
            docs = VectorRepository(aws_region=_AWS_REGION).find_by_content_id(
                body.content_id
            )
            if docs:
                article_chunks = [doc["text"] for doc in docs]
        except Exception:
            logger.exception("Failed to fetch article chunks from DynamoDB")

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
                f"[출처: {doc.metadata.content_id}]\n{doc.text}" for doc, _ in filtered
            ]
    except Exception:
        logger.exception("Failed to perform RAG search")

    # Step 3. 답변 생성
    result, references = AnswerService(
        aws_region=_BEDROCK_REGION, model=_BEDROCK_MODEL_SONNET
    ).answer(
        refined_title=body.refined_title,
        refined_content=body.refined_content,
        original_title=body.original_title,
        original_content=body.original_content,
        suggested_tags=body.suggested_tags,
        article_chunks=article_chunks,
        rag_chunks=rag_chunks,
    )

    # Step 4. references 기반 related_contents 주입
    if references:
        try:
            summaries = SummaryRepository(aws_region=_AWS_REGION).find_by_content_ids(
                references
            )
            result.related_contents = [
                RelatedContent(
                    content_id=s["content_id"],
                    one_line_summary=s["one_line_summary"],
                )
                for s in summaries
            ]
        except Exception:
            logger.exception("Failed to fetch related contents from DynamoDB")

    # Step 5. 답변 DynamoDB 저장 (fire-and-forget)
    try:
        AnswerRepository(aws_region=_AWS_REGION).save(
            result,
            question_id=body.question_id,
            content_id=body.content_id,
            title=body.refined_title,
            content=body.refined_content,
        )
    except Exception:
        logger.exception("Failed to save answer to DynamoDB")

    # Step 6. 질문 임베딩 저장 (fire-and-forget)
    if body.question_id:
        try:
            question_text = f"{body.refined_title}\n{body.refined_content}"
            QuestionEmbeddingOrchestrator(aws_region=_AWS_REGION).embed_and_store(
                question_id=body.question_id,
                text=question_text,
                suggested_tags=body.suggested_tags,
                content_id=body.content_id,
            )
        except Exception:
            logger.exception("Failed to embed question for RAG")

    # Step 7. 이벤트 로그 저장 (fire-and-forget, DP-252)
    if body.user_id:
        try:
            EventRepository(aws_region=_AWS_REGION).save_event(
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
        min_score=body.min_score,
        exclude_question_id=body.question_id,
    )

    # 이벤트 로그 저장 (fire-and-forget, DP-252)
    if body.user_id:
        try:
            EventRepository(aws_region=_AWS_REGION).save_event(
                user_id=body.user_id,
                event_type=EventType.SIMILAR_QUESTIONS_SEARCHED,
                question_id=body.question_id,
            )
        except Exception:
            logger.exception("Failed to save event log")

    return SimilarQuestionResponse(results=results, total=len(results))


@router.post(
    "/similar-contents",
    response_model=SimilarContentResponse,
    dependencies=[Depends(verify_internal_key)],
)
def search_similar_contents(body: SimilarContentRequest) -> SimilarContentResponse:
    """유사 콘텐츠 검색 (DP-288).

    FAISS devpick 인덱스에서 유사한 아티클을 검색한다.
    청크 레벨 결과를 content_id 기준 MAX 점수로 집계하여 반환한다.
    에러는 전역 핸들러(AIServiceError)가 처리한다.
    """
    results = SimilarContentService(
        aws_region=_AWS_REGION,
    ).search(
        text=body.text,
        top_k=body.top_k,
        min_score=body.min_score,
        exclude_content_id=body.content_id,
    )

    # 이벤트 로그 저장 (fire-and-forget, DP-252)
    if body.user_id:
        try:
            EventRepository(aws_region=_AWS_REGION).save_event(
                user_id=body.user_id,
                event_type=EventType.SIMILAR_CONTENTS_SEARCHED,
                content_id=body.content_id,
            )
        except Exception:
            logger.exception("Failed to save similar-contents event log")

    return SimilarContentResponse(results=results, total=len(results))


@router.post(
    "/report",
    response_model=InsightResponse,
    dependencies=[Depends(verify_internal_key)],
)
def create_insight(body: InsightRequest) -> InsightResponse:
    """주간 리포트 AI 인사이트 생성 (DP-259).

    백엔드가 주간 리포트 생성 후 호출한다.
    에러는 전역 핸들러(AIServiceError)가 처리한다.
    DynamoDB 저장 실패는 무시하고 InsightResponse를 반환한다.
    """
    # Step 0. 유저 관심 키워드 + 미탐색 태그 기반 추천 글 조회 (PostgreSQL)
    user_keywords: list[str] = []
    unmatched_keywords: list[str] = []
    recommended_contents: list[dict] = []
    if _DATABASE_URL:
        try:
            user_repo = UserRepository(database_url=_DATABASE_URL)
            user_keywords = user_repo.find_keywords_by_user_id(body.user_id)

            active_tags = {t.tag_name.lower() for t in body.activities.tag_activities}
            if not active_tags:
                active_tags = {t.tag.lower() for t in body.activities.top_tags}
            unmatched_keywords = [
                k for k in user_keywords if k.lower() not in active_tags
            ]

            if unmatched_keywords:
                recommended_contents = user_repo.find_contents_by_tag_names(
                    unmatched_keywords
                )
        except Exception:
            logger.exception(
                "Failed to fetch user keywords/recommendations from PostgreSQL"
            )

    # Step 1. 주간 AI 이벤트 카운트 (event_logs 조회)
    ai_events: dict = {"refine": 0, "answer": 0, "similar": 0}
    try:
        week_start_dt = datetime.fromisoformat(body.week_start).replace(
            tzinfo=timezone.utc
        )
        week_end_dt = datetime.fromisoformat(body.week_end).replace(tzinfo=timezone.utc)
        events = EventRepository(aws_region=_AWS_REGION).find_by_user(
            user_id=body.user_id,
            start=week_start_dt,
            end=week_end_dt,
        )
        ai_events = {
            "refine": sum(
                1 for e in events if e["event_type"] == EventType.QUESTION_REFINED.value
            ),
            "answer": sum(
                1 for e in events if e["event_type"] == EventType.ANSWER_GENERATED.value
            ),
            "similar": sum(
                1
                for e in events
                if e["event_type"] == EventType.SIMILAR_QUESTIONS_SEARCHED.value
            ),
        }
    except Exception:
        logger.exception("Failed to fetch AI event counts from DynamoDB")

    # Step 2. 읽은 글 / 스크랩한 글 one_line_summary 조회
    read_summaries: list[dict] = []
    scrapped_summaries: list[dict] = []
    try:
        repo = SummaryRepository(aws_region=_AWS_REGION)
        if body.activities.read_content_ids:
            read_summaries = repo.find_by_content_ids(body.activities.read_content_ids)
        if body.activities.scrapped_content_ids:
            scrapped_summaries = repo.find_by_content_ids(
                body.activities.scrapped_content_ids
            )
    except Exception:
        logger.exception("Failed to fetch article summaries from DynamoDB")

    # Step 3. 작성한 질문 텍스트 조회
    question_texts: list[str] = []
    if body.activities.question_ids:
        try:
            question_texts = QuestionVectorRepository(
                aws_region=_AWS_REGION
            ).find_texts_by_ids(body.activities.question_ids)
        except Exception:
            logger.exception("Failed to fetch question texts from DynamoDB")

    # Step 4. 인사이트 생성
    result = InsightService(
        aws_region=_BEDROCK_REGION, model=_BEDROCK_MODEL_HAIKU
    ).generate(
        activities=body.activities,
        ai_events=ai_events,
        read_summaries=read_summaries,
        scrapped_summaries=scrapped_summaries,
        question_texts=question_texts,
        week_start=body.week_start,
        week_end=body.week_end,
        user_keywords=user_keywords,
        unmatched_keywords=unmatched_keywords,
        recommended_contents=recommended_contents,
    )
    result.report_id = body.report_id

    # Step 5. 인사이트 DynamoDB 저장 (fire-and-forget)
    try:
        InsightRepository(aws_region=_AWS_REGION).save(
            report_id=body.report_id,
            user_id=body.user_id,
            response=result,
        )
    except Exception:
        logger.exception("Failed to save insight to DynamoDB")

    # Step 6. 이벤트 로그 저장 (fire-and-forget)
    try:
        EventRepository(aws_region=_AWS_REGION).save_event(
            user_id=body.user_id,
            event_type=EventType.INSIGHT_GENERATED,
        )
    except Exception:
        logger.exception("Failed to save insight event log")

    return result


@router.post(
    "/quiz",
    response_model=AllLevelsQuizResponse,
    dependencies=[Depends(verify_internal_key)],
)
def create_quiz(body: QuizRequest) -> AllLevelsQuizResponse:
    """콘텐츠 AI 퀴즈 생성 (DP-265).

    content_id당 3문제(객관식 2 + 주관식 1)를 생성하고 ai_quizzes에 저장한다.
    에러는 전역 핸들러(AIServiceError)가 처리한다.
    """
    try:
        preprocessed = PreprocessService().preprocess(body.text)
    except ValueError as exc:
        raise AIBadRequestError(str(exc)) from exc

    result = QuizService(
        aws_region=_BEDROCK_REGION, model=_BEDROCK_MODEL_HAIKU
    ).generate_all(
        content_id=body.content_id,
        text=preprocessed,
    )

    # DynamoDB 저장 (fire-and-forget)
    try:
        QuizRepository(aws_region=_AWS_REGION).save(result)
    except Exception:
        logger.exception("Failed to save quiz to DynamoDB")

    # 이벤트 로그 저장 (fire-and-forget)
    if body.user_id:
        try:
            EventRepository(aws_region=_AWS_REGION).save_event(
                user_id=body.user_id,
                event_type=EventType.QUIZ_GENERATED,
                content_id=body.content_id,
            )
        except Exception:
            logger.exception("Failed to save quiz event log")

    return result


@router.post(
    "/trends",
    response_model=TrendResponse,
    dependencies=[Depends(verify_internal_key)],
)
def create_trend(body: TrendGenerateRequest) -> TrendResponse:
    """트렌드 수동 생성 — 디버그·장애 복구용 (DP-385).

    자동 트리거는 run_trend_scheduler.py(DP-386)가 담당.
    콘텐츠 0건 → 400, 5건 미만 → 422.
    """
    if not _DATABASE_URL:
        raise HTTPException(
            status_code=500, detail="DATABASE_URL이 설정되지 않았습니다."
        )

    if body.period_start is None:
        period_start, period_end = compute_period(body.unit)
    else:
        period_start = body.period_start
        period_end = compute_period_end(body.unit, period_start)

    start_dt = datetime.combine(period_start, time.min)
    end_dt = datetime.combine(period_end, time.min)

    count = ContentRepository(_DATABASE_URL).count_by_published_range(start_dt, end_dt)
    if count == 0:
        raise HTTPException(status_code=400, detail="수집된 콘텐츠가 없습니다.")
    if count < 5:
        raise HTTPException(
            status_code=422, detail=f"콘텐츠가 {count}건으로 5건 미만입니다."
        )

    return TrendOrchestrator(
        database_url=_DATABASE_URL,
        aws_region=_AWS_REGION,
        model=_BEDROCK_MODEL_HAIKU,
    ).run(body.unit, period_start, period_end, force=body.force_refresh)


@router.get(
    "/trends/latest",
    response_model=TrendResponse,
    dependencies=[Depends(verify_internal_key)],
)
def get_latest_trend(unit: str, scope: str = "global") -> TrendResponse:
    """unit+scope 기준 최신 트렌드 스냅샷 조회 (DP-385).

    없으면 404. 디버그·헬스체크 용도.
    """
    if not _DATABASE_URL:
        raise HTTPException(
            status_code=500, detail="DATABASE_URL이 설정되지 않았습니다."
        )
    result = TrendSnapshotRepository(_DATABASE_URL).get_latest(unit, scope)
    if result is None:
        raise HTTPException(status_code=404, detail="트렌드 스냅샷이 없습니다.")
    return result


def _job_ai_service() -> JobAiService:
    return JobAiService(aws_region=_BEDROCK_REGION, model=_BEDROCK_MODEL_JOB_AI)


@router.post(
    "/jobs/parse-jd",
    response_model=ParseJdResponse,
    dependencies=[Depends(verify_internal_key)],
)
def parse_job_jd(body: ParseJdRequest) -> ParseJdResponse:
    """채용 JD 텍스트에서 필수/우대 기술만 추출 (본문 저장 없음)."""
    return _job_ai_service().parse_jd(body)


@router.post(
    "/jobs/interview-qa",
    dependencies=[Depends(verify_internal_key)],
)
def generate_job_interview_qa(body: InterviewQaRequest) -> dict:
    """공고·이력서 기반 면접 Q&A JSON 생성."""
    return _job_ai_service().interview_qa(body)


@router.post(
    "/jobs/skill-gap",
    response_model=SkillGapResponse,
    dependencies=[Depends(verify_internal_key)],
)
def job_skill_gap(body: SkillGapRequest) -> SkillGapResponse:
    """부족 기술 기반 로드맵·유튜브 힌트."""
    return _job_ai_service().skill_gap(body)


@router.post(
    "/resume/parse",
    dependencies=[Depends(verify_internal_key)],
)
def parse_uploaded_resume(body: ResumeParseRequest) -> dict:
    """추출된 이력서 텍스트 → 마스터 이력서 JSON(dict, camelCase 스키마)."""
    return _job_ai_service().parse_candidate_resume(body)


@router.post(
    "/resume/enrich",
    dependencies=[Depends(verify_internal_key)],
)
def enrich_uploaded_resume(body: ResumeEnrichRequest) -> dict:
    """1차 파싱 스냅샷과 원문 텍스트로 비어 있는 항목용 패치 JSON."""
    return _job_ai_service().enrich_candidate_resume(body)


@router.post(
    "/jobs/mock-interview/plan",
    response_model=MockInterviewPlan,
    dependencies=[Depends(verify_internal_key)],
)
def plan_mock_interview(body: MockInterviewPlanRequest) -> MockInterviewPlan:
    """모의면접 15문항 플랜 보강 — Spring 백업 플랜이 그대로 폴백된다."""
    return _job_ai_service().plan_mock_interview(body)


@router.post(
    "/jobs/mock-interview/turn",
    response_model=MockInterviewTurnResponse,
    dependencies=[Depends(verify_internal_key)],
)
def evaluate_mock_interview_turn(
    body: MockInterviewTurnRequest,
) -> MockInterviewTurnResponse:
    """모의면접 턴 평가 — 다음 행동(꼬리/재답변/다음) 결정."""
    return _job_ai_service().evaluate_mock_turn(body)


@router.post(
    "/jobs/mock-interview/finalize",
    response_model=MockInterviewFinalizeResponse,
    dependencies=[Depends(verify_internal_key)],
)
def finalize_mock_interview(
    body: MockInterviewFinalizeRequest,
) -> MockInterviewFinalizeResponse:
    """면접 종료 시 5개 영역 점수, QA별 모범답안, 종합 피드백 생성."""
    return _job_ai_service().finalize_mock_interview(body)
