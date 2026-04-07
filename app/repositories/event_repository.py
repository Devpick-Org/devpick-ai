"""AI 처리 이벤트 DynamoDB 저장 레이어 (DP-252)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

from app.schemas.event import EventType

logger = logging.getLogger(__name__)


def _dedup_sk(
    date_str: str, event_type: str, content_id: str | None, question_id: str | None
) -> str:
    """일별 중복 제거용 Sort Key를 생성한다.

    형식: {YYYY-MM-DD}#{event_type}#{content_id or ''}#{question_id or ''}
    """
    return f"{date_str}#{event_type}#{content_id or ''}#{question_id or ''}"


class EventRepository:
    """event_logs DynamoDB 테이블에 AI 처리 이벤트를 저장한다.

    테이블 스키마:
        PK: user_id (S)
        SK: {YYYY-MM-DD}#{event_type}#{content_id}#{question_id} (S)

    이 SK 설계를 통해 일별 중복 제거와 날짜 범위 조회 모두 지원한다.
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        table_name: str = "event_logs",
    ) -> None:
        self._table = boto3.resource("dynamodb", region_name=aws_region).Table(
            table_name
        )

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
        today_str = now.strftime("%Y-%m-%d")
        sk = _dedup_sk(today_str, event_type.value, content_id, question_id)

        # 이미 존재하면 스킵 (conditional_expression 대신 get_item으로 확인)
        existing = self._table.get_item(Key={"user_id": user_id, "sk": sk})
        if existing.get("Item"):
            logger.debug(
                "Skipping duplicate event: user_id=%s, event_type=%s, content_id=%s",
                user_id,
                event_type.value,
                content_id,
            )
            return

        now_iso = now.isoformat()
        item: dict = {
            "user_id": user_id,
            "sk": sk,
            "event_type": event_type.value,
            "content_id": content_id,
            "question_id": question_id,
            "metadata": metadata,
            "timestamp": now_iso,
            "created_at": now_iso,
        }
        self._table.put_item(Item=item)
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
        key_cond = Key("user_id").eq(user_id)

        # SK는 날짜 prefix로 시작하므로 범위 필터를 begins_with / between으로 처리
        if start and end:
            start_str = start.strftime("%Y-%m-%d")
            end_str = end.strftime("%Y-%m-%d")
            key_cond = key_cond & Key("sk").between(start_str, end_str + "\uffff")
        elif start:
            start_str = start.strftime("%Y-%m-%d")
            key_cond = key_cond & Key("sk").gte(start_str)
        elif end:
            end_str = end.strftime("%Y-%m-%d")
            key_cond = key_cond & Key("sk").lt(end_str)

        resp = self._table.query(
            KeyConditionExpression=key_cond,
            ScanIndexForward=False,  # 최신순
        )
        items = resp.get("Items", [])

        if event_type:
            items = [i for i in items if i.get("event_type") == event_type.value]

        return items
