"""Top 5 콘텐츠 주제 흐름 서사 요약 생성 서비스 (DP-404)."""

from __future__ import annotations

import logging

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from app.core.bedrock import to_tool_config
from app.core.exceptions import AIInternalError, AITimeoutError, AIUpstreamError
from app.core.prompts.trend_top_posts import (
    SYSTEM_PROMPT,
    TOOL_SAVE_TOP_POSTS_SUMMARY,
    build_user_prompt,
)
from app.repositories.summary_repository import SummaryRepository

logger = logging.getLogger(__name__)

_TOOL_NAME = "save_top_posts_summary"


class TopPostsSummaryGenerator:
    """기간 조회수 Top 5 콘텐츠의 주제 흐름을 LLM이 서사 요약한다."""

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        model: str = "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        summary_repo: SummaryRepository | None = None,
    ) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=aws_region,
            config=Config(read_timeout=120, retries={"max_attempts": 0}),
        )
        self._model = model
        self._summary_repo = summary_repo or SummaryRepository(aws_region=aws_region)

    def generate(
        self,
        top_contents: list[dict],
        unit: str,
        period_start: str = "",
        period_end: str = "",
        prev_summary: str | None = None,
    ) -> str | None:
        """Top 5 콘텐츠 주제 흐름을 LLM이 서사 요약한다.

        top_contents 빈 리스트 → None 반환.
        LLM 실패(AIUpstreamError, AITimeoutError) → None 반환 (스냅샷 저장 계속).
        prev_summary: 이전 기간 top_posts_summary — 있으면 프롬프트에 주입해 차이점 서술 유도.
        """
        if not top_contents:
            return None

        content_ids = [c["id"] for c in top_contents]
        summary_meta = self._summary_repo.find_summaries_for_trend(content_ids)
        user_prompt = build_user_prompt(
            top_contents, summary_meta, period_start, period_end, unit, prev_summary
        )

        try:
            response = self._client.converse(
                modelId=self._model,
                system=[
                    {"text": SYSTEM_PROMPT},
                    {"cachePoint": {"type": "default"}},
                ],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                toolConfig=to_tool_config(TOOL_SAVE_TOP_POSTS_SUMMARY, _TOOL_NAME),
                inferenceConfig={"maxTokens": 1024, "temperature": 0.4},
            )
        except ReadTimeoutError as exc:
            logger.warning("top_posts_summary 생성 타임아웃 — skip: %s", exc)
            raise AITimeoutError() from exc
        except EndpointConnectionError as exc:
            logger.warning("top_posts_summary 생성 연결 실패 — skip: %s", exc)
            raise AIUpstreamError() from exc
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if "ThrottlingException" in code or "ServiceUnavailable" in code:
                logger.warning("top_posts_summary Rate Limit — skip: %s", exc)
                raise AIUpstreamError() from exc
            raise AIUpstreamError(str(exc)) from exc

        content_blocks = response["output"]["message"]["content"]
        tool_use_block = next((b for b in content_blocks if "toolUse" in b), None)
        if not tool_use_block:
            raise AIInternalError("tool_use 블록 없음")

        return tool_use_block["toolUse"]["input"].get("top_posts_summary")
