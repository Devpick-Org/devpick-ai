"""AI 답변 결과 DynamoDB 저장 레이어 (DP-234)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import boto3

from app.schemas.answer import AnswerResponse

logger = logging.getLogger(__name__)


class AnswerRepository:
    """ai_answers DynamoDB 테이블에 AI 답변 결과를 저장한다.

    테이블 스키마:
        PK: question_id (S)
    question_id가 없는 경우 content_id를 PK 대용으로 사용한다.
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        table_name: str = "ai_answers",
    ) -> None:
        self._table = boto3.resource("dynamodb", region_name=aws_region).Table(
            table_name
        )

    def save(
        self,
        answer: AnswerResponse,
        question_id: str | None = None,
        content_id: str | None = None,
    ) -> None:
        """답변 결과를 저장한다.

        question_id가 있으면 upsert, 없으면 content_id를 키로 삼아 put_item.

        Args:
            answer: 저장할 AnswerResponse 객체.
            question_id: 질문 식별자 (upsert 키). None이면 content_id로 대체.
            content_id: 관련 아티클 ID.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        doc = answer.model_dump()
        doc["updated_at"] = now
        if content_id:
            doc["content_id"] = content_id

        pk = question_id or content_id or now
        doc["question_id"] = pk

        self._table.update_item(
            Key={"question_id": pk},
            UpdateExpression=(
                "SET "
                + ", ".join(
                    f"#{k} = :{k}"
                    for k in doc
                    if k != "question_id"
                )
                + ", created_at = if_not_exists(created_at, :created_at)"
            ),
            ExpressionAttributeNames={
                f"#{k}": k for k in doc if k != "question_id"
            },
            ExpressionAttributeValues={
                **{f":{k}": v for k, v in doc.items() if k != "question_id"},
                ":created_at": now,
            },
        )

        logger.info(
            "Saved answer to DynamoDB: question_id=%s, content_id=%s",
            question_id,
            content_id,
        )
