"""AI 답변 결과 MongoDB 저장 레이어 (DP-234)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo import MongoClient

from app.schemas.answer import AnswerResponse

logger = logging.getLogger(__name__)


class AnswerRepository:
    """ai_answers 컬렉션에 AI 답변 결과를 저장한다."""

    def __init__(self, mongo_uri: str, db_name: str = "devpick") -> None:
        self._client: MongoClient = MongoClient(mongo_uri)
        self._collection = self._client[db_name]["ai_answers"]

    def save(
        self,
        answer: AnswerResponse,
        question_id: str | None = None,
        content_id: str | None = None,
    ) -> None:
        """답변 결과를 저장한다.

        question_id가 있으면 upsert, 없으면 insert.

        Args:
            answer: 저장할 AnswerResponse 객체.
            question_id: 질문 식별자 (upsert 키). None이면 단순 insert.
            content_id: 관련 아티클 ID (조회용 인덱스).
        """
        now = datetime.now(tz=timezone.utc)
        doc = answer.model_dump()
        doc["updated_at"] = now
        if content_id:
            doc["content_id"] = content_id

        if question_id:
            doc["question_id"] = question_id
            self._collection.update_one(
                {"question_id": question_id},
                {
                    "$set": doc,
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
        else:
            doc["created_at"] = now
            self._collection.insert_one(doc)

        logger.info(
            "Saved answer to MongoDB: question_id=%s, content_id=%s",
            question_id,
            content_id,
        )
