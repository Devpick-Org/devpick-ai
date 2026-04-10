"""AI 퀴즈 결과 DynamoDB 저장 레이어 (DP-265)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from app.schemas.quiz import AllLevelsQuizResponse

logger = logging.getLogger(__name__)


def _sanitize(obj: object) -> object:
    """float을 Decimal로 재귀 변환한다 (DynamoDB float 미지원)."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


class QuizRepository:
    """ai_quizzes DynamoDB 테이블에 AI 퀴즈 결과를 저장한다.

    테이블 스키마:
        PK: content_id (S)
        SK: level (S)               — beginner / junior / mid / senior
        quiz_id (S)                 — 고유 식별자 (UUID)
        q1 / q2 / q3 (M)           — 문제별 개별 필드 (type/question/options/answer/explanation)
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        table_name: str = "ai_quizzes",
    ) -> None:
        self._table = boto3.resource("dynamodb", region_name=aws_region).Table(
            table_name
        )

    def save(self, response: AllLevelsQuizResponse) -> None:
        """4레벨 퀴즈를 ai_quizzes에 레벨별 개별 아이템으로 upsert한다.

        Args:
            response: AllLevelsQuizResponse 객체
        """
        now = datetime.now(tz=timezone.utc).isoformat()

        levels = {
            "beginner": response.beginner,
            "junior": response.junior,
            "mid": response.mid,
            "senior": response.senior,
        }

        for level_name, level_quiz in levels.items():
            self._table.update_item(
                Key={"content_id": response.content_id, "level": level_name},
                UpdateExpression=(
                    "SET quiz_id = :quiz_id"
                    ", questions = :questions"
                    ", generated_at = :generated_at"
                    ", updated_at = :updated_at"
                    ", created_at = if_not_exists(created_at, :created_at)"
                ),
                ExpressionAttributeValues={
                    ":quiz_id": response.quiz_id,
                    ":questions": _sanitize(
                        [q.model_dump() for q in level_quiz.questions]
                    ),
                    ":generated_at": response.generated_at,
                    ":updated_at": now,
                    ":created_at": now,
                },
            )

        logger.info(
            "Saved quiz to DynamoDB: content_id=%s (4 levels)", response.content_id
        )

    def find_by_content_id(self, content_id: str) -> list[dict]:
        """content_id로 전체 레벨 퀴즈를 조회한다."""
        resp = self._table.query(
            KeyConditionExpression=Key("content_id").eq(content_id)
        )
        return resp.get("Items", [])

    def find_by_content_id_and_level(self, content_id: str, level: str) -> dict | None:
        """content_id + level로 단건 조회한다."""
        resp = self._table.get_item(Key={"content_id": content_id, "level": level})
        return resp.get("Item")
