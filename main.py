from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.internal.router import router as internal_router

logger = logging.getLogger(__name__)

app = FastAPI(title="DevPick AI Server")

# 라우터 등록
app.include_router(internal_router)


# 기존 public health (유지)
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# 공통 에러 핸들러
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
