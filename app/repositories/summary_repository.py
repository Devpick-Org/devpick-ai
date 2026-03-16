"""AI 요약 결과 MongoDB 저장 레이어 (DP-220)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo import MongoClient

from app.schemas.summary import SummaryResponse

logger = logging.getLogger(__name__)


class SummaryRepository:
    """ai_summaries 컬렉션에 AI 요약 결과를 저장한다."""

    def __init__(self, mongo_uri: str, db_name: str = "devpick") -> None:
        self._client: MongoClient = MongoClient(mongo_uri)
        self._collection = self._client[db_name]["ai_summaries"]

    def save(self, summary: SummaryResponse) -> None:
        """요약 결과를 upsert한다. (content_id, level) 기준.

        Args:
            summary: 저장할 SummaryResponse 객체.
        """
        now = datetime.now(tz=timezone.utc)
        doc = summary.model_dump()
        doc["updated_at"] = now

        self._collection.update_one(
            {"content_id": doc["content_id"], "level": doc["level"]},
            {
                "$set": doc,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        logger.info(
            "Saved summary to MongoDB: content_id=%s, level=%s",
            summary.content_id,
            summary.level,
        )
