"""AI 요약 결과 MongoDB 저장 레이어 (DP-220)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo import MongoClient, UpdateOne

from app.schemas.summary import AllLevelsSummaryResponse, SummaryResponse

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

    def save_all_levels(
        self, content_id: str, response: AllLevelsSummaryResponse
    ) -> None:
        """4레벨 요약을 ai_summaries에 bulk upsert한다. (content_id, level) 기준.

        common 필드와 레벨별 필드를 병합하여 기존 ai_summaries 스키마와 호환되는
        문서 4개(beginner/junior/mid/senior)를 생성한다.

        Args:
            content_id: 콘텐츠 식별자
            response: AllLevelsSummaryResponse 객체
        """
        now = datetime.now(tz=timezone.utc)
        common = response.common.model_dump()

        ops = []
        for level in ("beginner", "junior", "mid", "senior"):
            level_data = getattr(response, level).model_dump()
            doc = {
                "content_id": content_id,
                "level": level,
                "generated_at": response.generated_at,
                "thumbnail_url": response.thumbnail_url,
                "updated_at": now,
                **common,
                **level_data,
            }
            ops.append(
                UpdateOne(
                    {"content_id": content_id, "level": level},
                    {"$set": doc, "$setOnInsert": {"created_at": now}},
                    upsert=True,
                )
            )

        self._collection.bulk_write(ops, ordered=False)
        logger.info("Saved all-levels summary to MongoDB: content_id=%s", content_id)

    def find_all_levels(self, content_id: str) -> list[dict]:
        """content_id에 대한 4개 레벨 문서 전부 조회한다.

        Args:
            content_id: 조회할 콘텐츠 식별자

        Returns:
            4개 레벨 문서 리스트 (없으면 빈 리스트)
        """
        return list(self._collection.find({"content_id": content_id}, {"_id": 0}))

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
