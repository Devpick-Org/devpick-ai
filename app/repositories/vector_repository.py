"""RAG 문서 DynamoDB 저장 레이어 (DP-218)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterator

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)


def _float_to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _embedding_to_dynamo(embedding: list[float]) -> list[Decimal]:
    return [_float_to_decimal(f) for f in embedding]


def _embedding_from_dynamo(embedding: list) -> list[float]:
    return [float(v) for v in embedding]


class VectorRepository:
    """rag_documents DynamoDB 테이블에 청크 + 임베딩 벡터를 저장한다.

    테이블 스키마:
        PK: content_id (S)
        SK: chunk_index (N)
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        table_name: str = "rag_documents",
    ) -> None:
        self._table = boto3.resource("dynamodb", region_name=aws_region).Table(
            table_name
        )

    def save_chunks(self, chunks: list[dict]) -> None:
        """청크 리스트를 upsert한다.

        Args:
            chunks: content_id, chunk_index, text, embedding, keywords, tags를 포함해야 한다.
        """
        if not chunks:
            return

        now = datetime.now(tz=timezone.utc).isoformat()
        for chunk in chunks:
            item = {
                "content_id": chunk["content_id"],
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"],
                "embedding": _embedding_to_dynamo(chunk.get("embedding", [])),
                "keywords": chunk.get("keywords", []),
                "tags": chunk.get("tags", []),
                "updated_at": now,
            }
            self._table.update_item(
                Key={
                    "content_id": chunk["content_id"],
                    "chunk_index": chunk["chunk_index"],
                },
                UpdateExpression=(
                    "SET #text = :text, embedding = :embedding, keywords = :keywords, "
                    "tags = :tags, updated_at = :updated_at, "
                    "created_at = if_not_exists(created_at, :created_at)"
                ),
                ExpressionAttributeNames={"#text": "text"},
                ExpressionAttributeValues={
                    ":text": item["text"],
                    ":embedding": item["embedding"],
                    ":keywords": item["keywords"],
                    ":tags": item["tags"],
                    ":updated_at": now,
                    ":created_at": now,
                },
            )

        logger.info(
            "rag_documents에 %d개 청크 저장 완료 (content_id=%s)",
            len(chunks),
            chunks[0].get("content_id"),
        )

    def find_by_content_id(self, content_id: str) -> list[dict]:
        """content_id로 청크를 조회한다 (복구/확인용)."""
        resp = self._table.query(
            KeyConditionExpression=Key("content_id").eq(content_id)
        )
        items = resp.get("Items", [])
        # embedding: Decimal → float 변환
        for item in items:
            if "embedding" in item:
                item["embedding"] = _embedding_from_dynamo(item["embedding"])
        return sorted(items, key=lambda x: int(x.get("chunk_index", 0)))

    def find_all(self) -> Iterator[dict]:
        """전체 청크를 순회한다 (FAISS 재빌드용)."""
        paginator = self._table.meta.client.get_paginator("scan")
        for page in paginator.paginate(TableName=self._table.name):
            for item in page.get("Items", []):
                if "embedding" in item:
                    item["embedding"] = _embedding_from_dynamo(item["embedding"])
                yield item

    def delete_by_content_id(self, content_id: str) -> int:
        """content_id의 모든 청크를 삭제한다.

        Returns:
            삭제된 문서 수
        """
        resp = self._table.query(
            KeyConditionExpression=Key("content_id").eq(content_id),
            ProjectionExpression="content_id, chunk_index",
        )
        items = resp.get("Items", [])
        count = 0
        for item in items:
            self._table.delete_item(
                Key={
                    "content_id": item["content_id"],
                    "chunk_index": item["chunk_index"],
                }
            )
            count += 1
        logger.info("content_id=%s 청크 %d개 삭제", content_id, count)
        return count
