"""SummaryService 단위 테스트 — mock 기반, 실제 API 호출 없음 (DP-219, DP-223)."""

from __future__ import annotations

import copy
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from app.core.exceptions import (
    AIBadRequestError,
    AIInternalError,
    AITimeoutError,
    AIUpstreamError,
)
from app.services.summary_service import SummaryService

_VALID_LLM_PAYLOAD = {
    "one_line_summary": "Redis 캐시를 활용한 TTL 설정 전략",
    "core_summary": [
        {
            "heading": "캐시 무효화의 필요성",
            "content": "데이터가 변경되면 캐시된 값은 유효하지 않다. 이를 방치하면 오래된 데이터가 노출된다.",
        },
        {
            "heading": "TTL 기반 전략",
            "content": "Redis EXPIRE 명령으로 키에 만료 시간을 설정한다. TTL이 지나면 자동 삭제된다.",
        },
    ],
    "key_points": ["TTL 설정", "캐시 무효화", "Redis 명령어"],
    "keywords": ["캐시 무효화", "TTL 설정", "EXPIRE"],
    "tags": ["Redis", "백엔드", "캐시"],
    "difficulty": "easy",
    "next_recommendation": "Redis Pub/Sub 패턴도 학습해보세요.",
    "study_questions": ["TTL이란 무엇인가?", "캐시 무효화 전략의 종류는?"],
    "confidence": 0.88,
}


def _make_service_with_mock(payload: dict) -> tuple[SummaryService, MagicMock]:
    """mock Anthropic 클라이언트를 주입한 SummaryService를 반환한다."""
    with patch("anthropic.Anthropic"):
        svc = SummaryService(api_key="test-key")

    mock_client = MagicMock()
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = payload
    mock_client.messages.create.return_value.content = [tool_block]
    svc._client = mock_client
    return svc, mock_client


def test_summarize_junior_success() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result = svc.summarize(
        content_id="art-001",
        level="junior",
        text="Redis TTL에 대한 글입니다.",
        thumbnail_url="https://example.com/thumb.png",
    )

    assert result.content_id == "art-001"
    assert result.level == "junior"
    assert isinstance(result.core_summary, list)
    assert result.core_summary[0].heading == "캐시 무효화의 필요성"
    assert isinstance(result.tags, list)
    assert "Redis" in result.tags
    assert result.thumbnail_url == "https://example.com/thumb.png"
    assert result.confidence == pytest.approx(0.88)


def test_summarize_mid_success() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result = svc.summarize(
        content_id="art-002",
        level="mid",
        text="Redis 실무 적용 패턴.",
    )

    assert result.level == "mid"
    assert result.one_line_summary == _VALID_LLM_PAYLOAD["one_line_summary"]


def test_summarize_senior_success() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result = svc.summarize(
        content_id="art-003",
        level="senior",
        text="Redis 아키텍처 트레이드오프 분석.",
    )

    assert result.level == "senior"
    assert result.thumbnail_url is None


def test_invalid_tool_response_raises() -> None:
    with patch("anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # tool_use 블록 없이 text 블록만 있는 응답
        text_block = MagicMock()
        text_block.type = "text"
        mock_client.messages.create.return_value.content = [text_block]

        svc = SummaryService(api_key="test-key")
        svc._client = mock_client

        with pytest.raises(AIInternalError, match="tool_use 블록이 없습니다"):
            svc.summarize(
                content_id="art-004",
                level="junior",
                text="유효한 텍스트.",
            )


def test_empty_text_raises() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    with pytest.raises(AIBadRequestError, match="요약할 텍스트가 없습니다"):
        svc.summarize(
            content_id="art-005",
            level="junior",
            text="",
        )


def test_invalid_level_raises() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    with pytest.raises(AIBadRequestError, match="지원하지 않는 레벨"):
        svc.summarize(
            content_id="art-006",
            level="expert",
            text="유효한 텍스트.",
        )


# ─── DP-223: SDK 예외 → 커스텀 예외 변환 단위 테스트 ───────────────────────


def _make_service_with_api_error(side_effect: Exception) -> SummaryService:
    """messages.create가 지정된 예외를 raise하는 SummaryService를 반환한다."""
    with patch("anthropic.Anthropic"):
        svc = SummaryService(api_key="test-key")
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = side_effect
    svc._client = mock_client
    return svc


def test_api_timeout_raises_ai_timeout_error() -> None:
    svc = _make_service_with_api_error(anthropic.APITimeoutError(request=MagicMock()))

    with pytest.raises(AITimeoutError):
        svc.summarize(content_id="art-t1", level="junior", text="텍스트.")


def test_rate_limit_raises_ai_upstream_error() -> None:
    svc = _make_service_with_api_error(
        anthropic.RateLimitError(
            message="rate limit",
            response=MagicMock(status_code=429),
            body={},
        )
    )

    with pytest.raises(AIUpstreamError):
        svc.summarize(content_id="art-t2", level="junior", text="텍스트.")


def test_api_connection_error_raises_ai_upstream_error() -> None:
    svc = _make_service_with_api_error(
        anthropic.APIConnectionError(request=MagicMock())
    )

    with pytest.raises(AIUpstreamError):
        svc.summarize(content_id="art-t3", level="junior", text="텍스트.")


def test_validation_error_raises_ai_internal_error() -> None:
    """SummaryResponse 파싱 실패 → AIInternalError."""
    with patch("anthropic.Anthropic"):
        svc = SummaryService(api_key="test-key")

    mock_client = MagicMock()
    # tool_use 블록은 있지만 필수 필드가 누락된 payload 반환
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {"one_line_summary": "요약"}  # 필수 필드 대부분 누락
    mock_client.messages.create.return_value.content = [tool_block]
    svc._client = mock_client

    with pytest.raises(AIInternalError, match="파싱"):
        svc.summarize(content_id="art-t4", level="junior", text="텍스트.")
