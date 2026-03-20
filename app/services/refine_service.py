"""AI 질문 개선 서비스 — Claude Tool Use + Prompt Caching (DP-231)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import anthropic
import pydantic

from app.core.exceptions import (
    AIBadRequestError,
    AIInternalError,
    AITimeoutError,
    AIUpstreamError,
)
from app.core.prompts.refine import REFINE_TOOL, SYSTEM_PROMPT, build_user_prompt
from app.schemas.refine import RefineResponse

logger = logging.getLogger(__name__)


class RefineService:
    """질문 개선을 수행하는 서비스."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
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
            AIInternalError: 인증 실패 / 파싱 실패 / tool_use 블록 없음
        """
        try:
            user_prompt = build_user_prompt(title, content, context_chunks)
        except ValueError as exc:
            raise AIBadRequestError(str(exc)) from exc

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                temperature=0,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
                tools=[REFINE_TOOL],
                tool_choice={"type": "tool", "name": "save_refined_question"},
            )
        except anthropic.APITimeoutError as exc:
            logger.warning("LLM 타임아웃: %s", exc)
            raise AITimeoutError() from exc
        except anthropic.RateLimitError as exc:
            logger.warning("LLM Rate Limit: %s", exc)
            raise AIUpstreamError("LLM Rate Limit 초과입니다") from exc
        except anthropic.APIConnectionError as exc:
            logger.error("LLM 연결 실패: %s", exc)
            raise AIUpstreamError("LLM 연결에 실패했습니다") from exc
        except anthropic.AuthenticationError as exc:
            logger.error("LLM 인증 실패: %s", exc)
            raise AIInternalError("LLM 인증에 실패했습니다") from exc
        except anthropic.APIStatusError as exc:
            logger.error("LLM API 상태 에러 (status=%s): %s", exc.status_code, exc)
            raise AIUpstreamError(f"LLM API 오류: {exc.status_code}") from exc

        # Tool Use 응답에서 input dict 추출
        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_blocks:
            logger.error(
                "LLM 응답에 tool_use 블록이 없습니다. content=%s", response.content
            )
            raise AIInternalError("LLM 응답에 tool_use 블록이 없습니다")

        try:
            payload = {
                **tool_blocks[0].input,
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            return RefineResponse.model_validate(payload)
        except pydantic.ValidationError as exc:
            logger.error("RefineResponse 파싱 실패: %s", exc)
            raise AIInternalError("AI 응답 파싱에 실패했습니다") from exc
