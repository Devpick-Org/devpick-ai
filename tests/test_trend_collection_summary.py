"""CollectionSummaryGenerator 단위 테스트 — mock 기반, 실제 API 호출 없음 (DP-384)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import EndpointConnectionError

from app.core.exceptions import AIInternalError
from app.services.trend.collection_summary import (
    CollectionSummaryGenerator,
    TrendSignals,
)
from app.services.trend.frequency import TagFrequency


def _make_generator(
    summary_text: str = "이번 주 수집 동향 요약",
) -> tuple[CollectionSummaryGenerator, MagicMock]:
    with patch("boto3.client"):
        gen = CollectionSummaryGenerator(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tool-1",
                            "name": "save_collection_summary",
                            "input": {"collection_summary": summary_text},
                        }
                    }
                ]
            }
        }
    }
    gen._client = mock_client
    return gen, mock_client


def _make_signals(unit: str = "weekly", **kwargs) -> TrendSignals:
    defaults = dict(
        unit=unit,
        period_start="2026-04-14",
        period_end="2026-04-21",
        cur_content_count=47,
        prev_content_count=38,
        top_tags=[
            TagFrequency(
                keyword="Kubernetes",
                cur_count=12,
                prev_count=8,
                delta=4,
                growth_rate=50.0,
                state="up",
            )
        ],
        tfidf_keywords=["서비스 메시", "무중단 배포", "헬스 체크"],
    )
    defaults.update(kwargs)
    return TrendSignals(**defaults)


# ── 정상 흐름 ─────────────────────────────────────────────────────────────────


def test_generate_returns_summary_on_success() -> None:
    gen, _ = _make_generator("이번 주 수집 동향 요약")

    result = gen.generate(_make_signals())

    assert result == "이번 주 수집 동향 요약"


# ── daily skip ────────────────────────────────────────────────────────────────


def test_generate_returns_none_for_daily() -> None:
    gen, mock_client = _make_generator()

    result = gen.generate(_make_signals(unit="daily"))

    assert result is None
    mock_client.converse.assert_not_called()


# ── LLM 실패 → None ──────────────────────────────────────────────────────────


def test_generate_returns_none_on_llm_failure() -> None:
    gen, mock_client = _make_generator()
    mock_client.converse.side_effect = EndpointConnectionError(
        endpoint_url="http://test"
    )

    result = gen.generate(_make_signals())

    assert result is None


# ── 프롬프트 검증 ─────────────────────────────────────────────────────────────


def test_generate_prompt_includes_content_count() -> None:
    gen, mock_client = _make_generator()

    gen.generate(_make_signals(cur_content_count=47, prev_content_count=38))

    user_text = mock_client.converse.call_args.kwargs["messages"][0]["content"][0][
        "text"
    ]
    assert "47" in user_text
    assert "38" in user_text


def test_generate_prompt_includes_tag_stats() -> None:
    gen, mock_client = _make_generator()

    gen.generate(_make_signals())

    user_text = mock_client.converse.call_args.kwargs["messages"][0]["content"][0][
        "text"
    ]
    assert "Kubernetes" in user_text
    assert "12" in user_text


def test_generate_with_prev_summary_includes_in_prompt() -> None:
    gen, mock_client = _make_generator()
    prev = "지난 주에는 React 중심의 프론트엔드 글이 많았습니다."

    gen.generate(_make_signals(prev_summary=prev))

    user_text = mock_client.converse.call_args.kwargs["messages"][0]["content"][0][
        "text"
    ]
    assert "이전 기간 collection_summary" in user_text
    assert prev in user_text


# ── tool_use 없음 → AIInternalError ──────────────────────────────────────────


def test_generate_raises_on_missing_tool_use() -> None:
    gen, mock_client = _make_generator()
    mock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "일반 텍스트 응답"}]}}
    }

    with pytest.raises(AIInternalError):
        gen.generate(_make_signals())
