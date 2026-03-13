from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import verify_internal_key

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/health", dependencies=[Depends(verify_internal_key)])
def internal_health() -> dict[str, str]:
    return {"status": "ok"}
