"""Unit tests for VelogBackfillCollector — mocks HTTP to test backfill/incremental behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from app.collectors.backfill.velog import VelogBackfillCollector, _parse_min_date
from app.schemas.normalized_content import NormalizedContent

# ── Fixtures ──────────────────────────────────────────────────────────────────

_POST = {
    "id": "post-001",
    "title": "Claude Code 완전 정복",
    "short_description": "AI 코딩 도구 가이드",
    "url_slug": "claude-code-guide",
    "released_at": "2026-03-15T10:00:00.000Z",
    "tags": ["AI", "개발도구"],
    "likes": 150,
    "comments_count": 12,
    "user": {"username": "devuser"},
}


def _graphql_resp(posts: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": {"trendingPosts": posts}}
    return resp


def _graphql_error_resp() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.HTTPError("400")
    return resp


# ── collect_batch_normalized — backfill phase ─────────────────────────────────


def test_backfill_returns_normalized_contents() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")
    resp = _graphql_resp([_POST])

    with patch.object(collector.session, "post", return_value=resp):
        items, cursor = collector.collect_batch_normalized({}, batch_size=10)

    assert len(items) == 1
    assert isinstance(items[0], NormalizedContent)
    assert items[0].source_name == "Velog"
    assert items[0].title == "Claude Code 완전 정복"
    assert items[0].canonical_url == "https://velog.io/@devuser/claude-code-guide"


def test_backfill_cursor_transitions_to_incremental() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")
    resp = _graphql_resp([_POST])

    with patch.object(collector.session, "post", return_value=resp):
        _, new_cursor = collector.collect_batch_normalized({}, batch_size=10)

    assert new_cursor == {"phase": "incremental"}


def test_backfill_falls_back_to_crawl_when_graphql_empty() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")
    empty_resp = _graphql_resp([])

    with patch.object(collector.session, "post", return_value=empty_resp):
        with patch.object(
            collector, "_crawl_trending", return_value=[_POST]
        ) as mock_crawl:
            items, _ = collector.collect_batch_normalized({}, batch_size=10)

    mock_crawl.assert_called_once()
    assert len(items) == 1


def test_backfill_falls_back_to_crawl_when_graphql_fails() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")

    with patch.object(collector.session, "post", return_value=_graphql_error_resp()):
        with patch.object(collector, "_crawl_trending", return_value=[]) as mock_crawl:
            items, _ = collector.collect_batch_normalized({}, batch_size=10)

    mock_crawl.assert_called_once()
    assert items == []


# ── collect_batch_normalized — incremental phase ──────────────────────────────


def test_incremental_phase_uses_week_timeframe() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")
    resp = _graphql_resp([_POST])

    with patch.object(collector.session, "post", return_value=resp) as mock_post:
        items, cursor = collector.collect_batch_normalized(
            {"phase": "incremental"}, batch_size=10
        )

    assert len(items) == 1
    payload = mock_post.call_args.kwargs["json"]
    assert payload["variables"]["input"]["timeframe"] == "week"


def test_incremental_cursor_unchanged() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")
    resp = _graphql_resp([_POST])
    original_cursor = {"phase": "incremental"}

    with patch.object(collector.session, "post", return_value=resp):
        _, new_cursor = collector.collect_batch_normalized(
            original_cursor, batch_size=10
        )

    assert new_cursor == original_cursor


# ── _to_normalized_content ────────────────────────────────────────────────────


def test_normalized_content_adr006_summary_only() -> None:
    """ADR-006: body_candidate=None, is_original_visible=False."""
    collector = VelogBackfillCollector(min_date="")
    result = collector._to_normalized_content(_POST)

    assert result is not None
    assert result.body_candidate is None
    assert result.is_original_visible is False
    assert result.license_type is None


def test_normalized_content_canonical_url() -> None:
    collector = VelogBackfillCollector(min_date="")
    result = collector._to_normalized_content(_POST)

    assert result is not None
    assert result.canonical_url == "https://velog.io/@devuser/claude-code-guide"


def test_normalized_content_min_date_filter_excludes_old_posts() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")
    old_post = {**_POST, "released_at": "2025-12-31T23:59:59.000Z"}

    result = collector._to_normalized_content(old_post)

    assert result is None


def test_normalized_content_no_url_slug_returns_none() -> None:
    collector = VelogBackfillCollector(min_date="")
    post = {**_POST, "url_slug": None}

    result = collector._to_normalized_content(post)

    assert result is None


def test_normalized_content_tags_and_likes() -> None:
    collector = VelogBackfillCollector(min_date="")
    result = collector._to_normalized_content(_POST)

    assert result is not None
    assert result.tags == ["AI", "개발도구"]
    assert result.likes == 150
    assert result.comments_count == 12


# ── _parse_min_date ───────────────────────────────────────────────────────────


def test_parse_min_date_valid() -> None:
    dt = _parse_min_date("2026-01-01")
    assert dt is not None
    assert dt.year == 2026


def test_parse_min_date_empty_returns_none() -> None:
    assert _parse_min_date("") is None


def test_parse_min_date_invalid_returns_none() -> None:
    assert _parse_min_date("NOT_A_DATE") is None
