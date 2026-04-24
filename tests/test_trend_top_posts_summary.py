"""TopPostsSummaryGenerator 단위 테스트 — mock 기반, 실제 API 호출 없음 (DP-404)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import EndpointConnectionError

from app.core.exceptions import AIUpstreamError
from app.services.trend.top_posts_summary import TopPostsSummaryGenerator


def _make_generator(
    summary_text: str = "이번 주 트렌드 요약",
) -> tuple[TopPostsSummaryGenerator, MagicMock]:
    """mock Bedrock 클라이언트와 mock SummaryRepo를 주입한 Generator를 반환한다."""
    mock_repo = MagicMock()
    mock_repo.find_summaries_for_trend.return_value = {}

    with patch("boto3.client"):
        gen = TopPostsSummaryGenerator(aws_region="us-east-1", summary_repo=mock_repo)

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tool-1",
                            "name": "save_top_posts_summary",
                            "input": {"top_posts_summary": summary_text},
                        }
                    }
                ]
            }
        }
    }
    gen._client = mock_client
    return gen, mock_client


def _make_top_contents(n: int = 2) -> list[dict]:
    return [
        {
            "id": f"cid-{i}",
            "title": f"글 {i}",
            "translated_title": None,
            "category": "Backend",
            "tags": '["Python"]',
            "source_id": "src-1",
            "published_at": None,
        }
        for i in range(1, n + 1)
    ]


# ── 정상 흐름 ─────────────────────────────────────────────────────────────────


def test_generate_returns_summary_on_success() -> None:
    gen, _ = _make_generator("이번 주 트렌드 요약")

    result = gen.generate(
        top_contents=_make_top_contents(),
        unit="weekly",
        period_start="2026-04-14",
        period_end="2026-04-21",
    )

    assert result == "이번 주 트렌드 요약"


# ── 빈 입력 ───────────────────────────────────────────────────────────────────


def test_generate_returns_none_for_empty_contents() -> None:
    gen, mock_client = _make_generator()

    result = gen.generate(top_contents=[], unit="weekly")

    assert result is None
    mock_client.converse.assert_not_called()


# ── LLM 실패 ─────────────────────────────────────────────────────────────────


def test_generate_raises_ai_upstream_error_on_llm_failure() -> None:
    gen, mock_client = _make_generator()
    mock_client.converse.side_effect = EndpointConnectionError(
        endpoint_url="http://test"
    )

    with pytest.raises(AIUpstreamError):
        gen.generate(top_contents=_make_top_contents(), unit="weekly")


# ── daily period label ────────────────────────────────────────────────────────


def test_generate_daily_period_label_uses_time_range() -> None:
    gen, mock_client = _make_generator()

    gen.generate(
        top_contents=_make_top_contents(),
        unit="daily",
        period_start="2026-04-24T08:00:00",
        period_end="2026-04-24T16:00:00",
    )

    call_messages = mock_client.converse.call_args.kwargs["messages"]
    user_text = call_messages[0]["content"][0]["text"]
    assert "4월 24일 8시~16시" in user_text


# ── prev_summary 주입 ─────────────────────────────────────────────────────────


def test_generate_with_prev_summary_includes_in_prompt() -> None:
    gen, mock_client = _make_generator()
    prev = "지난 주에는 Kubernetes 관련 글이 주목받았습니다."

    gen.generate(
        top_contents=_make_top_contents(),
        unit="weekly",
        prev_summary=prev,
    )

    call_messages = mock_client.converse.call_args.kwargs["messages"]
    user_text = call_messages[0]["content"][0]["text"]
    assert "이전 기간 요약" in user_text
    assert prev in user_text


# ── one_line_summary 누락 ─────────────────────────────────────────────────────


def test_generate_handles_missing_one_line_summary() -> None:
    mock_repo = MagicMock()
    mock_repo.find_summaries_for_trend.return_value = {}

    with patch("boto3.client"):
        gen = TopPostsSummaryGenerator(aws_region="us-east-1", summary_repo=mock_repo)

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tool-1",
                            "name": "save_top_posts_summary",
                            "input": {"top_posts_summary": "요약 결과"},
                        }
                    }
                ]
            }
        }
    }
    gen._client = mock_client

    result = gen.generate(top_contents=_make_top_contents(), unit="weekly")

    assert result == "요약 결과"
