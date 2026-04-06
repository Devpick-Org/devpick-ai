"""주간 인사이트 DynamoDB 저장 레이어 (DP-259)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import boto3

from app.schemas.insight import InsightResponse

logger = logging.getLogger(__name__)


class InsightRepository:
    """weekly_report_insights DynamoDB 테이블에 AI 인사이트를 저장한다.

    테이블 스키마:
        PK: report_id (S)

    필드명은 백엔드의 ReportInsightDocument와 1:1 대응 (snake_case):
      report_id, user_id, well_done, lacking, next_week, generated_at
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        table_name: str = "weekly_report_insights",
    ) -> None:
        self._table = boto3.resource("dynamodb", region_name=aws_region).Table(
            table_name
        )

    def save(self, report_id: str, user_id: str, response: InsightResponse) -> None:
        """인사이트를 upsert한다. report_id 기준.

        Args:
            report_id: 주간 리포트 UUID 문자열.
            user_id: 유저 UUID 문자열.
            response: 저장할 InsightResponse 객체.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        doc = {
            "user_id": user_id,
            "well_done": response.well_done,
            "lacking": response.lacking,
            "next_week": response.next_week,
            "generated_at": response.generated_at,
            "updated_at": now,
        }

        self._table.update_item(
            Key={"report_id": report_id},
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
        logger.info("Saved insight to DynamoDB: report_id=%s", report_id)

    def find_by_report_id(self, report_id: str) -> dict | None:
        """report_id로 인사이트를 조회한다.

        Args:
            report_id: 주간 리포트 UUID 문자열.

        Returns:
            인사이트 문서 또는 None.
        """
        resp = self._table.get_item(Key={"report_id": report_id})
        return resp.get("Item")
