"""Unit tests for VelogCollector — mocks HTTP to test collection behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from app.collectors.velog import VelogCollector
from app.schemas.normalized_content import NormalizedContent

# ── Helpers ──────────────────────────────────────────────────────────────────


def make_post(
    post_id: str = "post-abc",
    title: str = "Spring Boot 팁 모음",
    short_description: str = "짧은 설명입니다.",
    url_slug: str = "spring-boot-tips",
    released_at: str = "2026-05-01T12:00:00.000Z",  # 2026 so it passes min_date filter
    tags: list[str] | None = None,
    username: str = "devuser",
    likes: int = 42,
    comments_count: int = 7,
) -> dict:
    return {
        "id": post_id,
        "title": title,
        "short_description": short_description,
        "url_slug": url_slug,
        "released_at": released_at,
        "tags": tags if tags is not None else ["java", "spring"],
        "user": {"username": username},
        "likes": likes,
        "comments_count": comments_count,
    }


def mock_graphql_response(key: str, posts: list[dict]) -> MagicMock:
    """Build a mock response where data[key] = posts."""
    resp = MagicMock()
    resp.json.return_value = {"data": {key: posts}}
    resp.raise_for_status.return_value = None
    return resp


def mock_trending_response(posts: list[dict]) -> MagicMock:
    return mock_graphql_response("trendingPosts", posts)


def mock_posts_response(posts: list[dict]) -> MagicMock:
    return mock_graphql_response("posts", posts)


# ── fetch() — trendingPosts first, posts fallback ─────────────────────────────


def test_fetch_returns_normalized_contents() -> None:
    collector = VelogCollector()
    post = make_post()
    resp = mock_trending_response([post])

    with patch.object(collector.session, "post", return_value=resp):
        results = collector.fetch()

    assert len(results) == 1
    content = results[0]
    assert isinstance(content, NormalizedContent)
    assert content.source_name == "Velog"
    assert content.title == "Spring Boot 팁 모음"
    assert content.canonical_url == "https://velog.io/@devuser/spring-boot-tips"
    assert content.author == "devuser"
    assert content.is_original_visible is False  # ADR-006
    assert content.body_candidate is None  # ADR-006
    assert content.license_type is None
    assert content.likes == 42
    assert content.comments_count == 7


def test_fetch_tries_trending_posts_first() -> None:
    """fetch() must try trendingPosts before posts query."""
    collector = VelogCollector()
    post = make_post()
    trending_resp = mock_trending_response([post])

    with patch.object(
        collector.session, "post", return_value=trending_resp
    ) as mock_post:
        collector.fetch()

    # Only one call should have been made (trendingPosts), not two
    assert mock_post.call_count == 1
    call_payload = mock_post.call_args.kwargs["json"]
    assert call_payload["operationName"] == "TrendingPosts"


def test_fetch_falls_back_to_posts_when_trending_returns_empty() -> None:
    """When trendingPosts returns [], fetch() must fall back to posts query."""
    collector = VelogCollector()
    post = make_post()
    trending_empty = mock_trending_response([])
    posts_resp = mock_posts_response([post])

    with patch.object(
        collector.session, "post", side_effect=[trending_empty, posts_resp]
    ) as mock_post:
        results = collector.fetch()

    assert len(results) == 1
    assert mock_post.call_count == 2
    # Second call should be the Posts query
    second_payload = mock_post.call_args_list[1].kwargs["json"]
    assert second_payload["operationName"] == "Posts"


def test_fetch_falls_back_to_posts_when_trending_query_fails() -> None:
    """When trendingPosts raises, fetch() must fall back to posts query."""
    collector = VelogCollector()
    post = make_post()
    posts_resp = mock_posts_response([post])

    with patch.object(
        collector.session,
        "post",
        side_effect=[requests.ConnectionError("network error"), posts_resp],
    ):
        results = collector.fetch()

    assert len(results) == 1


def test_fetch_returns_empty_on_empty_api_response() -> None:
    """Both trendingPosts and posts return [] → empty result."""
    collector = VelogCollector()
    trending_empty = mock_trending_response([])
    posts_empty = mock_posts_response([])

    with patch.object(
        collector.session, "post", side_effect=[trending_empty, posts_empty]
    ):
        results = collector.fetch()

    assert results == []


def test_fetch_returns_empty_on_exception() -> None:
    """Both queries fail → empty result (no crash)."""
    collector = VelogCollector()

    with patch.object(
        collector.session, "post", side_effect=requests.ConnectionError("refused")
    ):
        results = collector.fetch()

    assert results == []


def test_fetch_returns_empty_on_http_error() -> None:
    collector = VelogCollector()
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.HTTPError("500")

    with patch.object(collector.session, "post", return_value=resp):
        results = collector.fetch()

    assert results == []


def test_fetch_trending_posts_sends_correct_variables() -> None:
    """trendingPosts must send limit=30, offset=0, timeframe='week'."""
    collector = VelogCollector()
    resp = mock_trending_response([])
    posts_resp = mock_posts_response([])

    with patch.object(
        collector.session, "post", side_effect=[resp, posts_resp]
    ) as mock_post:
        collector._fetch_trending_posts()

    call_payload = mock_post.call_args.kwargs["json"]
    variables = call_payload["variables"]
    assert variables["input"]["limit"] == 30
    assert variables["input"]["offset"] == 0
    assert variables["input"]["timeframe"] == "week"


# ── min_date filtering ────────────────────────────────────────────────────────


def test_fetch_filters_out_pre_min_date_posts() -> None:
    """Posts with released_at before min_date must be excluded."""
    collector = VelogCollector(min_date="2026-01-01")
    old_post = make_post(released_at="2025-12-31T23:59:59.000Z")
    resp = mock_trending_response([old_post])
    posts_empty = mock_posts_response([])

    with patch.object(collector.session, "post", side_effect=[resp, posts_empty]):
        results = collector.fetch()

    assert results == []


def test_fetch_keeps_posts_on_exact_min_date() -> None:
    """Posts with released_at == min_date (UTC midnight) must be included."""
    collector = VelogCollector(min_date="2026-01-01")
    post = make_post(released_at="2026-01-01T00:00:00.000Z")
    resp = mock_trending_response([post])

    with patch.object(collector.session, "post", return_value=resp):
        results = collector.fetch()

    assert len(results) == 1


def test_fetch_keeps_posts_after_min_date() -> None:
    """Posts with released_at after min_date must be included."""
    collector = VelogCollector(min_date="2026-01-01")
    post = make_post(released_at="2026-06-15T10:00:00.000Z")
    resp = mock_trending_response([post])

    with patch.object(collector.session, "post", return_value=resp):
        results = collector.fetch()

    assert len(results) == 1


def test_fetch_no_min_date_filter_when_not_set() -> None:
    """VelogCollector(min_date='') applies no date filter — old posts pass through."""
    collector = VelogCollector(min_date="")
    old_post = make_post(released_at="2020-01-01T00:00:00.000Z")
    resp = mock_trending_response([old_post])

    with patch.object(collector.session, "post", return_value=resp):
        results = collector.fetch()

    assert len(results) == 1


# ── _fetch_posts ──────────────────────────────────────────────────────────────


def test_fetch_posts_sends_origin_header() -> None:
    collector = VelogCollector()
    resp = mock_posts_response([])

    with patch.object(collector.session, "post", return_value=resp) as mock_post:
        collector._fetch_posts()

    call_headers = mock_post.call_args.kwargs["headers"]
    assert call_headers.get("Origin") == "https://velog.io"


def test_fetch_posts_sends_to_correct_endpoint() -> None:
    collector = VelogCollector()
    resp = mock_posts_response([])

    with patch.object(collector.session, "post", return_value=resp) as mock_post:
        collector._fetch_posts()

    assert mock_post.call_args.args[0] == "https://v3.velog.io/graphql"


def test_fetch_posts_returns_empty_on_missing_data_key() -> None:
    collector = VelogCollector()
    resp = MagicMock()
    resp.json.return_value = {}
    resp.raise_for_status.return_value = None

    with patch.object(collector.session, "post", return_value=resp):
        result = collector._fetch_posts()

    assert result == []


# ── _to_normalized_content ────────────────────────────────────────────────────


def test_to_normalized_content_builds_canonical_url() -> None:
    collector = VelogCollector()
    post = make_post(username="alice", url_slug="my-post")

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.canonical_url == "https://velog.io/@alice/my-post"


def test_to_normalized_content_null_user_uses_unknown() -> None:
    collector = VelogCollector()
    post = make_post()
    post["user"] = None

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.author == "Unknown"
    # "Unknown" is truthy → canonical_url is still built with it
    assert result.canonical_url == "https://velog.io/@Unknown/spring-boot-tips"


def test_to_normalized_content_null_username_canonical_url_uses_unknown() -> None:
    collector = VelogCollector()
    post = make_post()
    post["user"] = {"username": None}

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.author == "Unknown"


def test_to_normalized_content_null_url_slug_canonical_url_is_none() -> None:
    collector = VelogCollector()
    post = make_post()
    post["url_slug"] = None

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.canonical_url is None


def test_to_normalized_content_parses_released_at() -> None:
    collector = VelogCollector()
    post = make_post(released_at="2026-05-01T12:00:00.000Z")

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.published_at is not None
    assert "2026" in result.published_at


def test_to_normalized_content_null_released_at_gives_none_published() -> None:
    collector = VelogCollector(min_date="")  # disable date filter
    post = make_post(released_at=None)

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.published_at is None


def test_to_normalized_content_invalid_released_at_gives_none_published() -> None:
    collector = VelogCollector(min_date="")  # disable date filter
    post = make_post(released_at="NOT_A_DATE")

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.published_at is None


def test_to_normalized_content_old_post_returns_none() -> None:
    """Posts before min_date must return None so they are filtered out."""
    collector = VelogCollector(min_date="2026-01-01")
    post = make_post(released_at="2024-05-01T12:00:00.000Z")

    result = collector._to_normalized_content(post)

    assert result is None


def test_to_normalized_content_preview_truncated_at_260_chars() -> None:
    collector = VelogCollector()
    post = make_post(short_description="x" * 300)

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.preview is not None
    assert len(result.preview) == 260


def test_to_normalized_content_short_description_not_truncated() -> None:
    collector = VelogCollector()
    post = make_post(short_description="짧은 설명")

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.preview == "짧은 설명"


def test_to_normalized_content_null_tags_ignored() -> None:
    collector = VelogCollector()
    post = make_post()
    post["tags"] = None

    result = collector._to_normalized_content(post)

    assert result is not None


def test_to_normalized_content_body_candidate_always_none() -> None:
    """ADR-006: SUMMARY_ONLY — body_candidate must always be None for Velog."""
    collector = VelogCollector()
    post = make_post()

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.body_candidate is None


def test_to_normalized_content_is_original_visible_always_false() -> None:
    """ADR-006: SUMMARY_ONLY — is_original_visible must always be False for Velog."""
    collector = VelogCollector()
    post = make_post()

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.is_original_visible is False


def test_to_normalized_content_likes_and_comments_count() -> None:
    """likes and comments_count must be populated from the post data."""
    collector = VelogCollector()
    post = make_post(likes=123, comments_count=45)

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.likes == 123
    assert result.comments_count == 45


def test_to_normalized_content_null_likes_gives_none() -> None:
    collector = VelogCollector()
    post = make_post()
    post["likes"] = None

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.likes is None


def test_to_normalized_content_null_comments_count_gives_none() -> None:
    collector = VelogCollector()
    post = make_post()
    post["comments_count"] = None

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.comments_count is None
