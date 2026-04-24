"""수집 동향 서사 요약 생성 서비스 (DP-384)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from app.core.bedrock import to_tool_config
from app.core.exceptions import AIInternalError
from app.core.prompts.trend_collection import (
    SYSTEM_PROMPT,
    TOOL_SAVE_COLLECTION_SUMMARY,
    build_user_prompt,
)
from app.services.trend.frequency import TagFrequency

logger = logging.getLogger(__name__)

_TOOL_NAME = "save_collection_summary"


@dataclass
class TrendSignals:
    """CollectionSummaryGenerator 입력 데이터 — 오케스트레이터(DP-386)가 조립."""

    unit: str
    period_start: str
    period_end: str
    cur_content_count: int
    prev_content_count: int = 0
    top_tags: list[TagFrequency] = field(default_factory=list)
    tfidf_keywords: list[str] = field(default_factory=list)
    prev_summary: str | None = None


class CollectionSummaryGenerator:
    """기간 수집 통계를 기반으로 개발자 커뮤니티 동향을 LLM이 서사 요약한다."""

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        model: str = "global.anthropic.claude-sonnet-4-6",
    ) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=aws_region,
            config=Config(read_timeout=120, retries={"max_attempts": 0}),
        )
        self._model = model

    def generate(self, signals: TrendSignals) -> str | None:
        """수집 동향 서사 요약을 생성한다.

        unit="daily" → None 반환 (collection_summary는 주/월 단위만).
        LLM 실패 → None 반환 (스냅샷 저장 계속 진행).
        tool_use 블록 없음 → AIInternalError 전파.
        """
        if signals.unit == "daily":
            return None

        user_prompt = build_user_prompt(signals)

        try:
            response = self._client.converse(
                modelId=self._model,
                system=[
                    {
                        "text": SYSTEM_PROMPT,
                        "cacheControl": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                toolConfig=to_tool_config(TOOL_SAVE_COLLECTION_SUMMARY, _TOOL_NAME),
                inferenceConfig={"maxTokens": 1024, "temperature": 0.4},
            )
        except ReadTimeoutError as exc:
            logger.warning("collection_summary 타임아웃 — skip: %s", exc)
            return None
        except EndpointConnectionError as exc:
            logger.warning("collection_summary 연결 실패 — skip: %s", exc)
            return None
        except ClientError as exc:
            logger.warning("collection_summary LLM 에러 — skip: %s", exc)
            return None

        content_blocks = response["output"]["message"]["content"]
        tool_use_block = next((b for b in content_blocks if "toolUse" in b), None)
        if not tool_use_block:
            raise AIInternalError("tool_use 블록 없음")

        return tool_use_block["toolUse"]["input"].get("collection_summary")
