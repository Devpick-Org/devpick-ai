from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends

from app.api.deps import verify_internal_key
from app.core.exceptions import AIBadRequestError
from app.repositories.summary_repository import SummaryRepository
from app.schemas.summary import SummaryRequest, SummaryResponse
from app.services.embedding_service import EmbeddingOrchestrator
from app.services.preprocess_service import PreprocessService
from app.services.summary_service import SummaryService

load_dotenv()
_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_MONGO_URI = os.getenv("MONGO_URI", "")
_MONGO_DB = os.getenv("MONGO_DB", "devpick")
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

logger = logging.getLogger(__name__)

_LEVEL_MAP: dict[str, str] = {
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
