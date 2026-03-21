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

    def find_by_content_ids(self, content_ids: list[str]) -> list[dict]:
        """여러 content_id의 요약을 조회한다.

        related_contents 생성 시 one_line_summary를 가져오는 데 사용한다.
        level이 여러 개일 수 있으므로 content_id당 첫 번째 결과만 반환한다.

        Args:
            content_ids: 조회할 content_id 리스트.

        Returns:
            content_id와 one_line_summary만 포함한 dict 리스트.
        """
        if not content_ids:
            return []

        seen: set[str] = set()
        results = []
        cursor = self._collection.find(
            {"content_id": {"$in": content_ids}},
            {"content_id": 1, "one_line_summary": 1, "_id": 0},
        )
        for doc in cursor:
            cid = doc.get("content_id")
            if cid and cid not in seen:
                seen.add(cid)
                results.append(
                    {
                        "content_id": cid,
                        "one_line_summary": doc.get("one_line_summary", ""),
                    }
                )
        return results
