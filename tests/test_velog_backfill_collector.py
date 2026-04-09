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

_POST_WITH_BODY = {**_POST, "_body": "# Claude Code\n\n본문 내용입니다."}


def _graphql_resp(posts: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": {"trendingPosts": posts}}
    return resp


def _graphql_error_resp() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.HTTPError("400")
    return resp


def _body_resp(body: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": {"post": {"body": body}}}
    return resp


# ── collect_batch_normalized — backfill phase ─────────────────────────────────


def test_backfill_returns_normalized_contents() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")

    with patch.object(collector, "_fetch_graphql", return_value=[_POST]):
        with patch.object(
            collector, "_enrich_with_body", return_value=[_POST_WITH_BODY]
        ):
            items, cursor = collector.collect_batch_normalized({}, batch_size=10)

    assert len(items) == 1
    assert isinstance(items[0], NormalizedContent)
    assert items[0].source_name == "Velog"
    assert items[0].title == "Claude Code 완전 정복"
    assert items[0].canonical_url == "https://velog.io/@devuser/claude-code-guide"
    assert items[0].body_candidate == "# Claude Code\n\n본문 내용입니다."
    assert items[0].is_original_visible is True


def test_backfill_cursor_transitions_to_incremental() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")

    with patch.object(collector, "_fetch_graphql", return_value=[_POST]):
        with patch.object(
            collector, "_enrich_with_body", return_value=[_POST_WITH_BODY]
        ):
            _, new_cursor = collector.collect_batch_normalized({}, batch_size=10)

    assert new_cursor == {"phase": "incremental"}


def test_backfill_falls_back_to_crawl_when_graphql_empty() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")

    with patch.object(collector, "_fetch_graphql", return_value=[]):
        with patch.object(
            collector, "_crawl_trending", return_value=[_POST]
        ) as mock_crawl:
            with patch.object(
                collector, "_enrich_with_body", return_value=[_POST_WITH_BODY]
            ):
                items, _ = collector.collect_batch_normalized({}, batch_size=10)

    mock_crawl.assert_called_once()
    assert len(items) == 1


def test_backfill_falls_back_to_crawl_when_graphql_fails() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")

    with patch.object(collector.session, "post", return_value=_graphql_error_resp()):
        with patch.object(collector, "_crawl_trending", return_value=[]) as mock_crawl:
            with patch.object(collector, "_enrich_with_body", return_value=[]):
                items, _ = collector.collect_batch_normalized({}, batch_size=10)

    mock_crawl.assert_called_once()
    assert items == []


# ── collect_batch_normalized — incremental phase ──────────────────────────────


def test_incremental_phase_uses_week_timeframe() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")

    with patch.object(
        collector, "_fetch_graphql", return_value=[_POST]
    ) as mock_graphql:
        with patch.object(
            collector, "_enrich_with_body", return_value=[_POST_WITH_BODY]
        ):
            items, cursor = collector.collect_batch_normalized(
                {"phase": "incremental"}, batch_size=10
            )

    mock_graphql.assert_called_once_with(timeframe="week", limit=10)
    assert len(items) == 1


def test_incremental_cursor_unchanged() -> None:
    collector = VelogBackfillCollector(min_date="2026-01-01")
    original_cursor = {"phase": "incremental"}

    with patch.object(collector, "_fetch_graphql", return_value=[_POST]):
        with patch.object(
            collector, "_enrich_with_body", return_value=[_POST_WITH_BODY]
        ):
            _, new_cursor = collector.collect_batch_normalized(
                original_cursor, batch_size=10
            )

    assert new_cursor == original_cursor


# ── _fetch_post_body ──────────────────────────────────────────────────────────


def test_fetch_post_body_returns_markdown() -> None:
    collector = VelogBackfillCollector(min_date="")

    with patch.object(
        collector.session, "post", return_value=_body_resp("# 제목\n본문")
    ):
        body = collector._fetch_post_body("devuser", "my-post")

    assert body == "# 제목\n본문"


def test_fetch_post_body_returns_none_on_error() -> None:
    collector = VelogBackfillCollector(min_date="")

    with patch.object(
        collector.session, "post", side_effect=requests.ConnectionError("fail")
    ):
        body = collector._fetch_post_body("devuser", "my-post")

    assert body is None


def test_enrich_with_body_injects_body() -> None:
    collector = VelogBackfillCollector(min_date="")

    with patch.object(collector, "_fetch_post_body", return_value="# 본문"):
        enriched = collector._enrich_with_body([_POST])

    assert enriched[0]["_body"] == "# 본문"


# ── _to_normalized_content ────────────────────────────────────────────────────


def test_normalized_content_body_candidate_from_body_field() -> None:
    collector = VelogBackfillCollector(min_date="")
    result = collector._to_normalized_content(_POST_WITH_BODY)

    assert result is not None
    assert result.body_candidate == "# Claude Code\n\n본문 내용입니다."
    assert result.is_original_visible is True


def test_normalized_content_body_candidate_none_when_no_body() -> None:
    """본문 fetch 실패 시 body_candidate=None."""
    collector = VelogBackfillCollector(min_date="")
    result = collector._to_normalized_content(_POST)

    assert result is not None
    assert result.body_candidate is None


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


def test_normalized_content_license_type_none() -> None:
    collector = VelogBackfillCollector(min_date="")
    result = collector._to_normalized_content(_POST)

    assert result is not None
    assert result.license_type is None


# ── _parse_min_date ───────────────────────────────────────────────────────────


def test_parse_min_date_valid() -> None:
    dt = _parse_min_date("2026-01-01")
    assert dt is not None
    assert dt.year == 2026


def test_parse_min_date_empty_returns_none() -> None:
    assert _parse_min_date("") is None


def test_parse_min_date_invalid_returns_none() -> None:
    assert _parse_min_date("NOT_A_DATE") is None
