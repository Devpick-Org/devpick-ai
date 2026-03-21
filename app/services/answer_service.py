"""AI 1차 답변 서비스 — Claude Tool Use + Prompt Caching (DP-234)."""

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
from app.core.prompts.answer import ANSWER_TOOL, SYSTEM_PROMPT, build_user_prompt
from app.schemas.answer import AnswerResponse

logger = logging.getLogger(__name__)


class AnswerService:
    """기술 질문에 대한 AI 1차 답변을 생성하는 서비스."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def answer(
        self,
        refined_title: str,
        refined_content: str,
        original_title: str | None = None,
        original_content: str | None = None,
        suggested_tags: list[str] | None = None,
        article_chunks: list[str] | None = None,
        rag_chunks: list[str] | None = None,
    ) -> tuple[AnswerResponse, list[str]]:
        """기술 질문에 대한 AI 답변을 생성한다.

        Args:
            refined_title: 개선된 질문 제목 (RefineResponse.refined_title)
            refined_content: 개선된 질문 본문 (RefineResponse.refined_content)
            original_title: 원본 질문 제목 (사용자 이해 수준 파악용, optional)
            original_content: 원본 질문 본문 (optional)
            suggested_tags: Refine 추천 태그 (optional)
            article_chunks: 관련 아티클 청크 텍스트 리스트 (content_id 있을 때, optional)
            rag_chunks: RAG 유사 문서 청크 리스트 (optional)

        Returns:
            (AnswerResponse, references) 튜플.
            AnswerResponse의 related_contents는 빈 리스트 — 라우터에서 채움.
            references는 LLM이 활용한 content_id 리스트 (related_contents 조회용).

        Raises:
            AIBadRequestError: 빈 refined_title/refined_content
            AITimeoutError: LLM 타임아웃
            AIUpstreamError: LLM 연결 실패 / API 에러 / Rate Limit
            AIInternalError: 인증 실패 / 파싱 실패 / tool_use 블록 없음
        """
        try:
            user_prompt = build_user_prompt(
                refined_title=refined_title,
                refined_content=refined_content,
                original_title=original_title,
                original_content=original_content,
                suggested_tags=suggested_tags,
                article_chunks=article_chunks,
                rag_chunks=rag_chunks,
            )
        except ValueError as exc:
            raise AIBadRequestError(str(exc)) from exc

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                temperature=0,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
                tools=[ANSWER_TOOL],
                tool_choice={"type": "tool", "name": "save_answer"},
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

        # references는 related_contents 조회용 — AnswerResponse 필드가 아니므로 분리
        raw_input = dict(tool_blocks[0].input)
        references: list[str] = raw_input.pop("references", [])

        try:
            payload = {
                **raw_input,
                "related_contents": [],  # 라우터에서 채움
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            return AnswerResponse.model_validate(payload), references
        except pydantic.ValidationError as exc:
            logger.error("AnswerResponse 파싱 실패: %s", exc)
            raise AIInternalError("AI 응답 파싱에 실패했습니다") from exc
