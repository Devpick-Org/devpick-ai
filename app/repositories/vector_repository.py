"""RAG 문서 MongoDB 저장 레이어 (DP-218)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

from pymongo import MongoClient

logger = logging.getLogger(__name__)


class VectorRepository:
    """rag_documents 컬렉션에 청크 + 임베딩 벡터를 저장한다.

    (content_id, chunk_index) unique index 기준 upsert.
    FAISS 인덱스 유실 시 이 컬렉션에서 재빌드한다.
    """

    def __init__(self, mongo_uri: str, db_name: str = "devpick") -> None:
        self._client: MongoClient = MongoClient(mongo_uri)
        self._collection = self._client[db_name]["rag_documents"]

    def save_chunks(self, chunks: list[dict]) -> None:
        """청크 리스트를 bulk upsert한다.

        Args:
            chunks: 각 dict는 content_id, chunk_index, text,
                    embedding, keywords, tags를 포함해야 한다.
        """
        if not chunks:
            return

        now = datetime.now(tz=timezone.utc)
        for chunk in chunks:
            doc = {**chunk, "updated_at": now}
            self._collection.update_one(
                {
                    "content_id": chunk["content_id"],
                    "chunk_index": chunk["chunk_index"],
                },
                {
                    "$set": doc,
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )

        logger.info(
            "rag_documents에 %d개 청크 저장 완료 (content_id=%s)",
            len(chunks),
            chunks[0].get("content_id"),
        )

    def find_by_content_id(self, content_id: str) -> list[dict]:
        """content_id로 청크를 조회한다 (복구/확인용)."""
        return list(
            self._collection.find(
                {"content_id": content_id},
                {"_id": 0},
            ).sort("chunk_index", 1)
        )

    def find_all(self) -> Iterator[dict]:
        """전체 청크를 순회한다 (FAISS 재빌드용)."""
        for doc in self._collection.find({}, {"_id": 0}):
            yield doc

    def delete_by_content_id(self, content_id: str) -> int:
        """content_id의 모든 청크를 삭제한다.

        Returns:
            삭제된 문서 수
        """
        result = self._collection.delete_many({"content_id": content_id})
        logger.info("content_id=%s 청크 %d개 삭제", content_id, result.deleted_count)
        return result.deleted_count
