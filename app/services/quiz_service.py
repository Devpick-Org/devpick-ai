"""AI 퀴즈 생성 서비스 — Bedrock Converse API + Tool Use (DP-265)."""

from __future__ import annotations

import logging
import uuid
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
from app.core.prompts.quiz import QUIZ_TOOL, SYSTEM_PROMPT_QUIZ, build_user_prompt
from app.schemas.quiz import AllLevelsQuizResponse

logger = logging.getLogger(__name__)

_TOOL_NAME = "save_quiz"


class QuizService:
    """기술 블로그 글에서 4레벨 퀴즈를 Bedrock Claude 1회 호출로 생성한다."""

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        model: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
    ) -> None:
        self._client = boto3.client("bedrock-runtime", region_name=aws_region)
        self._model = model

    def generate_all(self, content_id: str, text: str) -> AllLevelsQuizResponse:
        """4개 레벨 퀴즈(객관식 2 + 주관식 1)를 동시 생성한다.

        Args:
            content_id: 콘텐츠 식별자
            text: 전처리된 아티클 텍스트 (PreprocessService 출력)

        Returns:
            AllLevelsQuizResponse

        Raises:
            AIBadRequestError: 빈 text
            AITimeoutError: LLM 타임아웃
            AIUpstreamError: LLM 연결 실패 / API 에러 / Rate Limit
            AIInternalError: 파싱 실패 / tool_use 블록 없음
        """
        try:
            user_prompt = build_user_prompt(text)
        except ValueError as exc:
            raise AIBadRequestError(str(exc)) from exc

        try:
            response = self._client.converse(
                modelId=self._model,
                system=[
                    {"text": SYSTEM_PROMPT_QUIZ},
                    {"cachePoint": {"type": "default"}},
                ],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                toolConfig=to_tool_config(QUIZ_TOOL, _TOOL_NAME),
                inferenceConfig={"maxTokens": 4096, "temperature": 0.0},
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

        content = response["output"]["message"]["content"]
        tool_use_block = next((b for b in content if "toolUse" in b), None)
        if not tool_use_block:
            logger.error("LLM 응답에 toolUse 블록이 없습니다. content=%s", content)
            raise AIInternalError("LLM 응답에 tool_use 블록이 없습니다")

        try:
            payload = {
                **tool_use_block["toolUse"]["input"],
                "content_id": content_id,
                "quiz_id": str(uuid.uuid4()),
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            return AllLevelsQuizResponse.model_validate(payload)
        except pydantic.ValidationError as exc:
            logger.error("AllLevelsQuizResponse 파싱 실패: %s", exc)
            raise AIInternalError("AI 응답 파싱에 실패했습니다") from exc
