"""4레벨 동시 AI 요약 서비스 — Claude Tool Use + Prompt Caching (DP-300)."""

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
from app.core.prompts.summary import (
    SUMMARY_ALL_LEVELS_TOOL,
    SYSTEM_PROMPT_ALL_LEVELS,
    build_user_prompt_all_levels,
)
from app.schemas.summary import AllLevelsSummaryResponse

logger = logging.getLogger(__name__)


class AllLevelsSummaryService:
    """beginner/junior/mid/senior 4레벨 요약을 Claude API 1회 호출로 생성한다."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def summarize_all(
        self,
        content_id: str,
        text: str,
        thumbnail_url: str | None = None,
    ) -> AllLevelsSummaryResponse:
        """콘텐츠를 4개 레벨로 동시에 요약한다.

        Args:
            content_id: 콘텐츠 식별자
            text: 전처리된 아티클 텍스트 (PreprocessService 출력)
            thumbnail_url: 호출자가 주입하는 썸네일 URL (AI 생성 아님)

        Returns:
            AllLevelsSummaryResponse

        Raises:
            AIBadRequestError: 빈 text
            AITimeoutError: LLM 타임아웃
            AIUpstreamError: LLM 연결 실패 / API 에러 / Rate Limit
            AIInternalError: 인증 실패 / 파싱 실패 / tool_use 블록 없음
        """
        try:
            user_prompt = build_user_prompt_all_levels(text)
        except ValueError as exc:
            raise AIBadRequestError(str(exc)) from exc

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=8192,
                temperature=0,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT_ALL_LEVELS,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
                tools=[SUMMARY_ALL_LEVELS_TOOL],
                tool_choice={"type": "tool", "name": "save_all_summaries"},
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
                "content_id": content_id,
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                "thumbnail_url": thumbnail_url,
            }
            return AllLevelsSummaryResponse.model_validate(payload)
        except pydantic.ValidationError as exc:
            logger.error("AllLevelsSummaryResponse 파싱 실패: %s", exc)
            raise AIInternalError("AI 응답 파싱에 실패했습니다") from exc
