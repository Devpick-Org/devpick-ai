"""InsightService 단위 테스트 — mock 기반, 실제 API 호출 없음 (DP-259)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import anthropic
import pytest

from app.core.exceptions import AIInternalError, AITimeoutError, AIUpstreamError
from app.schemas.insight import ActivityData
from app.services.insight_service import InsightService

_VALID_LLM_PAYLOAD = {
    "well_done": "이번 주에 Redis와 Spring Boot 관련 글 5편을 읽었습니다.",
    "lacking": "다만 주중 특정 요일에 활동이 집중되었습니다.",
    "next_week": "다음 주에는 Docker 관련 학습을 이어가보세요.",
}


def _make_service_with_mock(payload: dict) -> tuple[InsightService, MagicMock]:
    """mock Anthropic 클라이언트를 주입한 InsightService를 반환한다."""
    with patch("anthropic.Anthropic"):
        svc = InsightService(api_key="test-key")

    mock_client = MagicMock()
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = payload
    mock_client.messages.create.return_value.content = [tool_block]
    svc._client = mock_client
    return svc, mock_client


def test_generate_success_returns_insight_response() -> None:
    svc, _ = _make_service_with_mock(_VALID_LLM_PAYLOAD.copy())

    result = svc.generate(
        activities=ActivityData(contents_read=5, questions_created=2, scraps_count=3),
        ai_events={"refine": 1, "answer": 2, "similar": 3},
        read_summaries=[{"one_line_summary": "Redis TTL 관리 전략"}],
        scrapped_summaries=[{"one_line_summary": "Spring Boot 가이드"}],
        question_texts=["Redis TTL 설정 방법은?"],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )

    assert result.well_done == _VALID_LLM_PAYLOAD["well_done"]
    assert result.lacking == _VALID_LLM_PAYLOAD["lacking"]
    assert result.next_week == _VALID_LLM_PAYLOAD["next_week"]
    assert result.report_id == ""  # 라우터에서 주입
    assert result.generated_at  # ISO 8601 문자열


def test_generate_sets_generated_at() -> None:
    svc, _ = _make_service_with_mock(_VALID_LLM_PAYLOAD.copy())

    result = svc.generate(
        activities=ActivityData(),
        ai_events={},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )

    assert "T" in result.generated_at  # ISO 8601 포맷 확인


def test_no_tool_use_block_raises_ai_internal_error() -> None:
    with patch("anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        text_block = MagicMock()
        text_block.type = "text"
        mock_client.messages.create.return_value.content = [text_block]

        svc = InsightService(api_key="test-key")
        svc._client = mock_client

        with pytest.raises(AIInternalError, match="tool_use 블록이 없습니다"):
            svc.generate(
                activities=ActivityData(),
                ai_events={},
                read_summaries=[],
                scrapped_summaries=[],
                question_texts=[],
                week_start="2026-03-17",
                week_end="2026-03-23",
            )


def test_validation_error_raises_ai_internal_error() -> None:
    svc, _ = _make_service_with_mock(
        {"well_done": "잘했어요"}
    )  # lacking, next_week 누락

    with pytest.raises(AIInternalError, match="파싱"):
        svc.generate(
            activities=ActivityData(),
            ai_events={},
            read_summaries=[],
            scrapped_summaries=[],
            question_texts=[],
            week_start="2026-03-17",
            week_end="2026-03-23",
        )


# ─── SDK 예외 → 커스텀 예외 변환 ────────────────────────────────────────────


def _make_service_with_api_error(side_effect: Exception) -> InsightService:
    with patch("anthropic.Anthropic"):
        svc = InsightService(api_key="test-key")
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = side_effect
    svc._client = mock_client
    return svc


def test_api_timeout_raises_ai_timeout_error() -> None:
    svc = _make_service_with_api_error(anthropic.APITimeoutError(request=MagicMock()))

    with pytest.raises(AITimeoutError):
        svc.generate(
            activities=ActivityData(),
            ai_events={},
            read_summaries=[],
            scrapped_summaries=[],
            question_texts=[],
            week_start="2026-03-17",
            week_end="2026-03-23",
        )


def test_rate_limit_raises_ai_upstream_error() -> None:
    svc = _make_service_with_api_error(
        anthropic.RateLimitError(
            message="rate limit",
            response=MagicMock(status_code=429),
            body={},
        )
    )

    with pytest.raises(AIUpstreamError):
        svc.generate(
            activities=ActivityData(),
            ai_events={},
            read_summaries=[],
            scrapped_summaries=[],
            question_texts=[],
            week_start="2026-03-17",
            week_end="2026-03-23",
        )


def test_api_connection_error_raises_ai_upstream_error() -> None:
    svc = _make_service_with_api_error(
        anthropic.APIConnectionError(request=MagicMock())
    )

    with pytest.raises(AIUpstreamError):
        svc.generate(
            activities=ActivityData(),
            ai_events={},
            read_summaries=[],
            scrapped_summaries=[],
            question_texts=[],
            week_start="2026-03-17",
            week_end="2026-03-23",
        )
