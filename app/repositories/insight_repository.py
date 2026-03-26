"""주간 인사이트 MongoDB 저장 레이어 (DP-259)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo import MongoClient

from app.schemas.insight import InsightResponse

logger = logging.getLogger(__name__)


class InsightRepository:
    """weekly_report_insights 컬렉션에 AI 인사이트를 저장한다.

    백엔드의 ReportInsightDocument와 필드명 일치 (직접 MongoDB 공유):
      report_id, user_id, well_done, lacking, next_week, generated_at
    """

    def __init__(self, mongo_uri: str, db_name: str = "devpick") -> None:
        self._client: MongoClient = MongoClient(mongo_uri)
        self._collection = self._client[db_name]["weekly_report_insights"]

    def save(self, report_id: str, user_id: str, response: InsightResponse) -> None:
        """인사이트를 upsert한다. report_id 기준.

        Args:
            report_id: 주간 리포트 UUID 문자열.
            user_id: 유저 UUID 문자열.
            response: 저장할 InsightResponse 객체.
        """
        now = datetime.now(tz=timezone.utc)
        doc = {
            "report_id": report_id,
            "user_id": user_id,
            "well_done": response.well_done,
            "lacking": response.lacking,
            "next_week": response.next_week,
            "generated_at": response.generated_at,
            "updated_at": now,
        }

        self._collection.update_one(
            {"report_id": report_id},
            {
                "$set": doc,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        logger.info("Saved insight to MongoDB: report_id=%s", report_id)

    def find_by_report_id(self, report_id: str) -> dict | None:
        """report_id로 인사이트를 조회한다.

        Args:
            report_id: 주간 리포트 UUID 문자열.

        Returns:
            인사이트 문서 또는 None.
        """
        return self._collection.find_one({"report_id": report_id}, {"_id": 0})
