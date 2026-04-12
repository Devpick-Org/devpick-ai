"""AI 질문 개선 서비스 — Bedrock Converse API + Tool Use (DP-231)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import boto3
import pydantic
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from app.core.bedrock import to_tool_config
from app.core.exceptions import (
    AIBadRequestError,
    AIInternalError,
    AITimeoutError,
    AIUpstreamError,
)
from app.core.prompts.refine import REFINE_TOOL, SYSTEM_PROMPT, build_user_prompt
from app.schemas.refine import RefineResponse

logger = logging.getLogger(__name__)

_TOOL_NAME = "save_refined_question"


class RefineService:
    """질문 개선을 수행하는 서비스."""

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        model: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
    ) -> None:
        self._client = boto3.client("bedrock-runtime", region_name=aws_region)
        self._model = model

    def refine(
        self,
        title: str,
        content: str,
        context_chunks: list[str] | None = None,
    ) -> RefineResponse:
        """질문을 개선한다.

        Args:
            title: 원본 질문 제목
            content: 원본 질문 본문
            context_chunks: 관련 아티클 청크 텍스트 리스트 (optional)

        Returns:
            RefineResponse

        Raises:
            AIBadRequestError: 빈 title/content
            AITimeoutError: LLM 타임아웃
            AIUpstreamError: LLM 연결 실패 / API 에러 / Rate Limit
            AIInternalError: 파싱 실패 / tool_use 블록 없음
        """
        try:
            user_prompt = build_user_prompt(title, content, context_chunks)
        except ValueError as exc:
            raise AIBadRequestError(str(exc)) from exc

        try:
            response = self._client.converse(
                modelId=self._model,
                system=[
                    {"text": SYSTEM_PROMPT},
                ],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                toolConfig=to_tool_config(REFINE_TOOL, _TOOL_NAME),
                inferenceConfig={"maxTokens": 1024, "temperature": 0.0},
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
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            return RefineResponse.model_validate(payload)
        except pydantic.ValidationError as exc:
            logger.error("RefineResponse 파싱 실패: %s", exc)
            raise AIInternalError("AI 응답 파싱에 실패했습니다") from exc
