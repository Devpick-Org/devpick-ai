"""질문 임베딩 MongoDB 저장 레이어 (DP-234)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

from pymongo import MongoClient

logger = logging.getLogger(__name__)


class QuestionVectorRepository:
    """rag_questions 컬렉션에 질문 임베딩을 저장한다."""

    def __init__(self, mongo_uri: str, db_name: str = "devpick") -> None:
        self._client: MongoClient = MongoClient(mongo_uri)
        self._collection = self._client[db_name]["rag_questions"]

    def save_question(
        self,
        question_id: str,
        text: str,
        embedding: list[float],
        suggested_tags: list[str] | None = None,
        content_id: str | None = None,
    ) -> None:
        """질문 임베딩을 upsert한다. question_id 기준.

        Args:
            question_id: 질문 식별자 (upsert 키).
            text: 임베딩 대상 텍스트 (refined_title + refined_content).
            embedding: 1536차원 임베딩 벡터.
            suggested_tags: 추천 태그 리스트 (optional).
            content_id: 관련 아티클 ID (optional).
        """
        now = datetime.now(tz=timezone.utc)
        doc: dict = {
            "question_id": question_id,
            "text": text,
            "embedding": embedding,
            "suggested_tags": suggested_tags or [],
            "updated_at": now,
        }
        if content_id:
            doc["content_id"] = content_id

        self._collection.update_one(
            {"question_id": question_id},
            {
                "$set": doc,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        logger.info("Saved question embedding to MongoDB: question_id=%s", question_id)

    def find_all(self) -> Iterator[dict]:
        """모든 질문 임베딩을 반환한다. FAISS 재빌드용."""
        return self._collection.find({})

    def find_texts_by_ids(self, question_ids: list[str]) -> list[str]:
        """question_id 목록으로 질문 텍스트를 조회한다. 주간 인사이트 생성용 (DP-259).

        Args:
            question_ids: 조회할 question_id 리스트.

        Returns:
            질문 텍스트 리스트 (순서 보장 없음, 없는 ID 무시).
        """
        if not question_ids:
            return []
        cursor = self._collection.find(
            {"question_id": {"$in": question_ids}},
            {"text": 1, "_id": 0},
        )
        return [doc["text"] for doc in cursor if doc.get("text")]
