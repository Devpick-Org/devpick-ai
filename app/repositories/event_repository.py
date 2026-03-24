"""AI 처리 이벤트 MongoDB 저장 레이어 (DP-252)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo import DESCENDING, MongoClient

from app.schemas.event import EventType

logger = logging.getLogger(__name__)


class EventRepository:
    """event_logs 컬렉션에 AI 처리 이벤트를 저장한다."""

    def __init__(self, mongo_uri: str, db_name: str = "devpick") -> None:
        self._client: MongoClient = MongoClient(mongo_uri)
        self._collection = self._client[db_name]["event_logs"]

    def save_event(
        self,
        user_id: str,
        event_type: EventType,
        content_id: str | None = None,
        question_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """이벤트를 저장한다. 당일 동일 이벤트가 존재하면 스킵한다.

        일별 중복 제거: (user_id, event_type, content_id, question_id) 조합이
        오늘 UTC 기준으로 이미 존재하면 저장하지 않는다.

        Args:
            user_id: 유저 식별자.
            event_type: AI 처리 이벤트 유형.
            content_id: 관련 콘텐츠 ID (optional).
            question_id: 관련 질문 ID (optional).
            metadata: 추가 컨텍스트 데이터 (optional).
        """
        now = datetime.now(tz=timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        existing = self._collection.find_one(
            {
                "user_id": user_id,
                "event_type": event_type.value,
                "content_id": content_id,
                "question_id": question_id,
                "timestamp": {"$gte": today_start},
            }
        )
        if existing:
            logger.debug(
                "Skipping duplicate event: user_id=%s, event_type=%s, content_id=%s",
                user_id,
                event_type.value,
                content_id,
            )
            return

        doc: dict = {
            "user_id": user_id,
            "event_type": event_type.value,
            "content_id": content_id,
            "question_id": question_id,
            "metadata": metadata,
            "timestamp": now,
            "created_at": now,
        }
        self._collection.insert_one(doc)
        logger.info(
            "Saved event log: user_id=%s, event_type=%s, content_id=%s",
            user_id,
            event_type.value,
            content_id,
        )

    def find_by_user(
        self,
        user_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        event_type: EventType | None = None,
    ) -> list[dict]:
        """유저의 이벤트를 조회한다 (Epic F 주간 리포트용).

        Args:
            user_id: 유저 식별자.
            start: 조회 시작 시각 (inclusive).
            end: 조회 종료 시각 (exclusive).
            event_type: 특정 이벤트 유형 필터 (optional).

        Returns:
            이벤트 문서 리스트 (최신순).
        """
        query: dict = {"user_id": user_id}
        if start or end:
            ts_filter: dict = {}
            if start:
                ts_filter["$gte"] = start
            if end:
                ts_filter["$lt"] = end
            query["timestamp"] = ts_filter
        if event_type:
            query["event_type"] = event_type.value

        return list(
            self._collection.find(query, {"_id": 0}).sort("timestamp", DESCENDING)
        )
