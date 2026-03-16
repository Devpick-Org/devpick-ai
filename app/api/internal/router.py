from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import verify_internal_key
from app.schemas.summary import SummaryRequest, SummaryResponse
from app.services.preprocess_service import PreprocessService
from app.services.summary_service import SummaryService

load_dotenv()
_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

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
    level = _LEVEL_MAP.get(body.level)
    if level is None:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 레벨: {body.level!r}. JUNIOR/MIDDLE/SENIOR 또는 junior/mid/senior 사용",
        )

    try:
        preprocessed = PreprocessService().preprocess(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = SummaryService(api_key=_ANTHROPIC_API_KEY).summarize(
            content_id=body.content_id,
            level=level,
            text=preprocessed,
            thumbnail_url=body.thumbnail_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result
