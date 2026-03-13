from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import Header, HTTPException

load_dotenv()
_INTERNAL_KEY = os.getenv("INTERNAL_API_KEY", "")


def verify_internal_key(x_internal_key: str = Header(...)) -> None:
    if not _INTERNAL_KEY or x_internal_key != _INTERNAL_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
