"""질문 임베딩 DynamoDB 저장 레이어 (DP-234)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterator

import boto3

logger = logging.getLogger(__name__)


def _embedding_to_dynamo(embedding: list[float]) -> list[Decimal]:
    return [Decimal(str(f)) for f in embedding]


def _embedding_from_dynamo(embedding: list) -> list[float]:
    return [float(v) for v in embedding]


class QuestionVectorRepository:
    """rag_questions DynamoDB 테이블에 질문 임베딩을 저장한다.

    테이블 스키마:
        PK: question_id (S)
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        table_name: str = "rag_questions",
    ) -> None:
        self._table = boto3.resource("dynamodb", region_name=aws_region).Table(
            table_name
        )

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
            embedding: 1024차원 임베딩 벡터.
            suggested_tags: 추천 태그 리스트 (optional).
            content_id: 관련 아티클 ID (optional).
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        doc: dict = {
            "text": text,
            "embedding": _embedding_to_dynamo(embedding),
            "suggested_tags": suggested_tags or [],
            "updated_at": now,
        }
        if content_id:
            doc["content_id"] = content_id

        self._table.update_item(
            Key={"question_id": question_id},
            UpdateExpression=(
                "SET "
                + ", ".join(f"#{k} = :{k}" for k in doc)
                + ", created_at = if_not_exists(created_at, :created_at)"
            ),
            ExpressionAttributeNames={f"#{k}": k for k in doc},
            ExpressionAttributeValues={
                **{f":{k}": v for k, v in doc.items()},
                ":created_at": now,
            },
        )
        logger.info("Saved question embedding to DynamoDB: question_id=%s", question_id)

    def delete_by_question_id(self, question_id: str) -> None:
        """질문 삭제 시 rag_questions 행을 제거한다. 없는 키여도 멱등."""
        self._table.delete_item(Key={"question_id": question_id})
        logger.info("Deleted rag_questions row: question_id=%s", question_id)

    def find_all(self) -> Iterator[dict]:
        """모든 질문 임베딩을 반환한다. FAISS 재빌드용."""
        paginator = self._table.meta.client.get_paginator("scan")
        for page in paginator.paginate(TableName=self._table.name):
            for item in page.get("Items", []):
                if "embedding" in item:
                    item["embedding"] = _embedding_from_dynamo(item["embedding"])
                yield item

    def find_texts_by_ids(self, question_ids: list[str]) -> list[str]:
        """question_id 목록으로 질문 텍스트를 조회한다. 주간 인사이트 생성용 (DP-259).

        Args:
            question_ids: 조회할 question_id 리스트.

        Returns:
            질문 텍스트 리스트 (순서 보장 없음, 없는 ID 무시).
        """
        if not question_ids:
            return []

        texts: list[str] = []
        for qid in question_ids:
            resp = self._table.get_item(
                Key={"question_id": qid},
                ProjectionExpression="#t",
                ExpressionAttributeNames={"#t": "text"},
            )
            item = resp.get("Item")
            if item and item.get("text"):
                texts.append(item["text"])
        return texts
