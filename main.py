from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.internal.router import router as internal_router
from app.core.exceptions import AIServiceError

logger = logging.getLogger(__name__)

app = FastAPI(title="DevPick AI Server")

# 라우터 등록
app.include_router(internal_router)


# 기존 public health (유지)
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# AI 서비스 에러 핸들러 (AIServiceError 계층 전체)
@app.exception_handler(AIServiceError)
async def ai_service_error_handler(
    request: Request, exc: AIServiceError
) -> JSONResponse:
    logger.warning("AI service error (status=%s): %s", exc.status_code, exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


# 최종 방어선 — 처리되지 않은 예외
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
