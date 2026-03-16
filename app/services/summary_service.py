"""AI 요약 서비스 — Claude Tool Use + Prompt Caching (DP-219)."""

from __future__ import annotations

from datetime import datetime, timezone

import anthropic

from app.core.prompts.summary import SUMMARY_TOOL, SYSTEM_PROMPT, build_user_prompt
from app.schemas.summary import SummaryResponse


class SummaryService:
    """레벨별 콘텐츠 요약을 수행하는 서비스."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def summarize(
        self,
        content_id: str,
        level: str,
        text: str,
        thumbnail_url: str | None = None,
    ) -> SummaryResponse:
        """콘텐츠를 지정 레벨로 요약한다.

        Args:
            content_id: 콘텐츠 식별자
            level: "junior" | "mid" | "senior"
            text: 전처리된 아티클 텍스트 (PreprocessService 출력)
            thumbnail_url: 호출자가 주입하는 썸네일 URL (AI 생성 아님)

        Returns:
            SummaryResponse

        Raises:
            ValueError: 잘못된 level 또는 빈 text
        """
        user_prompt = build_user_prompt(level, text)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            temperature=0,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
            tools=[SUMMARY_TOOL],
            tool_choice={"type": "tool", "name": "save_summary"},
        )

        # Tool Use 응답에서 input dict 추출
        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_blocks:
            raise ValueError("LLM 응답에 tool_use 블록이 없습니다")

        payload = {
            **tool_blocks[0].input,
            "content_id": content_id,
            "level": level,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "thumbnail_url": thumbnail_url,
        }
        return SummaryResponse.model_validate(payload)
