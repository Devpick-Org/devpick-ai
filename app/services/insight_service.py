"""주간 인사이트 생성 서비스 — Bedrock Converse API + Tool Use (DP-259)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import boto3
import pydantic
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from app.core.bedrock import to_tool_config
from app.core.exceptions import (
    AIInternalError,
    AITimeoutError,
    AIUpstreamError,
)
from app.core.prompts.insight import INSIGHT_TOOL, SYSTEM_PROMPT, build_user_prompt
from app.schemas.insight import ActivityData, InsightResponse

logger = logging.getLogger(__name__)

_TOOL_NAME = "save_insight"


class InsightService:
    """유저 주간 활동 데이터를 분석해 학습 인사이트를 생성한다."""

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        model: str = "global.anthropic.claude-sonnet-4-6",
    ) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=aws_region,
            config=Config(read_timeout=300, retries={"max_attempts": 0}),
        )
        self._model = model
        logger.info("InsightService 초기화 — model=%s", self._model)

    def generate(
        self,
        activities: ActivityData,
        ai_events: dict,
        read_summaries: list[dict],
        scrapped_summaries: list[dict],
        question_texts: list[str],
        week_start: str,
        week_end: str,
    ) -> InsightResponse:
        """주간 활동 데이터를 기반으로 인사이트를 생성한다.

        Args:
            activities: 백엔드가 전달한 주간 활동 집계.
            ai_events: AI 기능 활용 카운트 {"refine": int, "answer": int, "similar": int}.
            read_summaries: 읽은 글 one_line_summary 목록.
            scrapped_summaries: 스크랩한 글 one_line_summary 목록.
            question_texts: 작성한 질문 텍스트 목록.
            week_start: 기간 시작 (ISO date 문자열).
            week_end: 기간 종료 (ISO date 문자열).

        Returns:
            InsightResponse (report_id는 빈 문자열 — 라우터에서 주입)

        Raises:
            AITimeoutError: LLM 타임아웃
            AIUpstreamError: LLM 연결 실패 / API 에러 / Rate Limit
            AIInternalError: 파싱 실패 / tool_use 블록 없음
        """
        user_prompt = build_user_prompt(
            activities=activities,
            ai_events=ai_events,
            read_summaries=read_summaries,
            scrapped_summaries=scrapped_summaries,
            question_texts=question_texts,
            week_start=week_start,
            week_end=week_end,
        )

        try:
            response = self._client.converse(
                modelId=self._model,
                system=[
                    {"text": SYSTEM_PROMPT},
                ],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                toolConfig=to_tool_config(INSIGHT_TOOL, _TOOL_NAME),
                inferenceConfig={"maxTokens": 1024, "temperature": 0.3},
            )
        except ReadTimeoutError as exc:
            logger.warning("LLM 타임아웃: %s", exc)
            raise AITimeoutError() from exc
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "ThrottlingException":
                logger.warning("LLM Rate Limit: %s", exc)
                raise AIUpstreamError("LLM Rate Limit 초과입니다") from exc
            logger.error("LLM API 오류 (code=%s): %s", code, exc)
            raise AIUpstreamError(f"LLM API 오류: {code}") from exc
        except EndpointConnectionError as exc:
            logger.error("LLM 연결 실패: %s", exc)
            raise AIUpstreamError("LLM 연결에 실패했습니다") from exc

        content_blocks = response["output"]["message"]["content"]
        tool_use_block = next((b for b in content_blocks if "toolUse" in b), None)
        if not tool_use_block:
            logger.error(
                "LLM 응답에 toolUse 블록이 없습니다. content=%s", content_blocks
            )
            raise AIInternalError("LLM 응답에 tool_use 블록이 없습니다")

        try:
            payload = {
                **tool_use_block["toolUse"]["input"],
                "report_id": "",  # 라우터에서 주입
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            return InsightResponse.model_validate(payload)
        except pydantic.ValidationError as exc:
            logger.error("InsightResponse 파싱 실패: %s", exc)
            raise AIInternalError("AI 응답 파싱에 실패했습니다") from exc
