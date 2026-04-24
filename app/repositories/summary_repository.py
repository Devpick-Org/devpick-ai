"""AI 요약 결과 DynamoDB 저장 레이어 (DP-220, DP-300)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from app.schemas.summary import AllLevelsSummaryResponse

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


class SummaryRepository:
    """ai_summaries DynamoDB 테이블에 AI 요약 결과를 저장한다.

    테이블 스키마:
        PK: content_id (S)
        SK: level (S)  — beginner / junior / mid / senior
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        table_name: str = "ai_summaries",
    ) -> None:
        self._dynamodb = boto3.resource("dynamodb", region_name=aws_region)
        self._table = self._dynamodb.Table(table_name)
        self._table_name = table_name

    def save_all_levels(
        self, content_id: str, response: AllLevelsSummaryResponse
    ) -> None:
        """4레벨 요약을 ai_summaries에 upsert한다. (content_id, level) 기준.

        Args:
            content_id: 콘텐츠 식별자
            response: AllLevelsSummaryResponse 객체
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        common = response.common.model_dump()

        for level in ("beginner", "junior", "mid", "senior"):
            level_data = getattr(response, level).model_dump()
            item = _sanitize(
                {
                    "content_id": content_id,
                    "level": level,
                    "generated_at": response.generated_at or now,
                    "thumbnail_url": response.thumbnail_url,
                    "title": response.title,
                    "translated_title": response.translated_title,
                    "updated_at": now,
                    "expires_at": (
                        datetime.now(tz=timezone.utc) + timedelta(days=7)
                    ).isoformat(),
                    **common,
                    **level_data,
                }
            )
            # if_not_exists(created_at, :now) — 최초 삽입 시에만 created_at 설정
            self._table.update_item(
                Key={"content_id": content_id, "level": level},
                UpdateExpression=(
                    "SET "
                    + ", ".join(
                        f"#{k} = :{k}" for k in item if k not in ("content_id", "level")
                    )
                    + ", created_at = if_not_exists(created_at, :created_at)"
                ),
                ExpressionAttributeNames={
                    f"#{k}": k for k in item if k not in ("content_id", "level")
                },
                ExpressionAttributeValues={
                    **{
                        f":{k}": v
                        for k, v in item.items()
                        if k not in ("content_id", "level")
                    },
                    ":created_at": now,
                },
            )

        logger.info("Saved all-levels summary to DynamoDB: content_id=%s", content_id)

    def find_meta_by_content_ids(self, content_ids: list[str]) -> dict[str, dict]:
        """여러 content_id의 beginner 레벨 tags·category를 batch로 조회한다.

        DynamoDB batch_get_item 최대 100개 제한으로 청크 분할 처리.
        반환: {content_id: {"tags": [...], "category": str}} — 없는 항목은 포함 안 함.
        """
        if not content_ids:
            return {}

        keys = [{"content_id": cid, "level": "beginner"} for cid in content_ids]
        result: dict[str, dict] = {}

        for i in range(0, len(keys), 100):
            chunk = keys[i : i + 100]
            resp = self._dynamodb.batch_get_item(
                RequestItems={self._table_name: {"Keys": chunk}}
            )
            for item in resp.get("Responses", {}).get(self._table_name, []):
                cid = item.get("content_id")
                if cid:
                    result[cid] = {
                        "tags": list(item.get("tags", [])),
                        "category": item.get("category"),
                    }

        return result

    def find_all_levels(self, content_id: str) -> list[dict]:
        """content_id에 대한 4개 레벨 문서 전부 조회한다."""
        resp = self._table.query(
            KeyConditionExpression=Key("content_id").eq(content_id)
        )
        return resp.get("Items", [])

    def find_summaries_for_trend(self, content_ids: list[str]) -> dict[str, dict]:
        """트렌드 top_posts_summary 용 mid 레벨 요약 메타 배치 조회.

        Returns:
            {content_id: {one_line_summary, keywords, tags, category}}
        누락 항목은 빈 값/빈 리스트로 처리.
        """
        if not content_ids:
            return {}

        keys = [{"content_id": cid, "level": "mid"} for cid in content_ids]
        result: dict[str, dict] = {}

        for i in range(0, len(keys), 100):
            chunk = keys[i : i + 100]
            resp = self._dynamodb.batch_get_item(
                RequestItems={self._table_name: {"Keys": chunk}}
            )
            for item in resp.get("Responses", {}).get(self._table_name, []):
                cid = item.get("content_id")
                if cid:
                    result[cid] = {
                        "one_line_summary": item.get("one_line_summary", ""),
                        "keywords": list(item.get("keywords", [])),
                        "tags": list(item.get("tags", [])),
                        "category": item.get("category", ""),
                    }

        return result

    def find_by_content_ids(self, content_ids: list[str]) -> list[dict]:
        """여러 content_id의 요약을 조회한다.

        related_contents 생성 시 one_line_summary를 가져오는 데 사용한다.
        content_id당 첫 번째 레벨(junior 우선) 결과만 반환한다.
        """
        if not content_ids:
            return []

        results = []
        seen: set[str] = set()
        for cid in content_ids:
            if cid in seen:
                continue
            resp = self._table.query(
                KeyConditionExpression=Key("content_id").eq(cid),
                Limit=1,
            )
            items = resp.get("Items", [])
            if items:
                doc = items[0]
                seen.add(cid)
                results.append(
                    {
                        "content_id": cid,
                        "one_line_summary": doc.get("one_line_summary", ""),
                    }
                )
        return results
