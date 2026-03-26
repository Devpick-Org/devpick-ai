"""주간 인사이트 생성 서비스 — Claude Tool Use + Prompt Caching (DP-259)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import anthropic
import pydantic

from app.core.exceptions import (
    AIInternalError,
    AITimeoutError,
    AIUpstreamError,
)
from app.core.prompts.insight import INSIGHT_TOOL, SYSTEM_PROMPT, build_user_prompt
from app.schemas.insight import ActivityData, InsightResponse

logger = logging.getLogger(__name__)


class InsightService:
    """유저 주간 활동 데이터를 분석해 학습 인사이트를 생성한다."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

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
            AIInternalError: 인증 실패 / 파싱 실패 / tool_use 블록 없음
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
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                temperature=0.3,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
                tools=[INSIGHT_TOOL],
                tool_choice={"type": "tool", "name": "save_insight"},
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

        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_blocks:
            logger.error(
                "LLM 응답에 tool_use 블록이 없습니다. content=%s", response.content
            )
            raise AIInternalError("LLM 응답에 tool_use 블록이 없습니다")

        try:
            payload = {
                **tool_blocks[0].input,
                "report_id": "",  # 라우터에서 주입
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            return InsightResponse.model_validate(payload)
        except pydantic.ValidationError as exc:
            logger.error("InsightResponse 파싱 실패: %s", exc)
            raise AIInternalError("AI 응답 파싱에 실패했습니다") from exc
