"""Unit tests for VelogCollector — mocks HTTP to test collection behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.collectors.velog import VelogCollector
from app.schemas.normalized_content import NormalizedContent


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_post(
    post_id: str = "post-abc",
    title: str = "Spring Boot 팁 모음",
    short_description: str = "짧은 설명입니다.",
    url_slug: str = "spring-boot-tips",
    released_at: str = "2024-05-01T12:00:00.000Z",
    tags: list[str] | None = None,
    username: str = "devuser",
) -> dict:
    return {
        "id": post_id,
        "title": title,
        "short_description": short_description,
        "url_slug": url_slug,
        "released_at": released_at,
        "tags": tags if tags is not None else ["java", "spring"],
        "user": {"username": username},
    }


def mock_post_response(posts: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"data": {"posts": posts}}
    resp.raise_for_status.return_value = None
    return resp


# ── fetch() — top-level pipeline ─────────────────────────────────────────────


def test_fetch_returns_normalized_contents() -> None:
    collector = VelogCollector()
    post = make_post()
    resp = mock_post_response([post])

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


def test_fetch_returns_empty_on_empty_api_response() -> None:
    collector = VelogCollector()
    resp = mock_post_response([])

    with patch.object(collector.session, "post", return_value=resp):
        results = collector.fetch()

    assert results == []


def test_fetch_returns_empty_on_exception() -> None:
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


# ── _fetch_posts ──────────────────────────────────────────────────────────────


def test_fetch_posts_sends_origin_header() -> None:
    collector = VelogCollector()
    resp = mock_post_response([])

    with patch.object(collector.session, "post", return_value=resp) as mock_post:
        collector._fetch_posts()

    call_headers = mock_post.call_args.kwargs["headers"]
    assert call_headers.get("Origin") == "https://velog.io"


def test_fetch_posts_sends_to_correct_endpoint() -> None:
    collector = VelogCollector()
    resp = mock_post_response([])

    with patch.object(collector.session, "post", return_value=resp) as mock_post:
        collector._fetch_posts()

    assert mock_post.call_args.args[0] == "https://v2.velog.io/graphql"


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
    post = make_post(released_at="2024-05-01T12:00:00.000Z")

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.published_at is not None
    assert "2024" in result.published_at


def test_to_normalized_content_null_released_at_gives_none_published() -> None:
    collector = VelogCollector()
    post = make_post(released_at=None)

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.published_at is None


def test_to_normalized_content_invalid_released_at_gives_none_published() -> None:
    collector = VelogCollector()
    post = make_post(released_at="NOT_A_DATE")

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.published_at is None


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


def test_to_normalized_content_null_tags_uses_empty_list() -> None:
    collector = VelogCollector()
    post = make_post()
    post["tags"] = None

    result = collector._to_normalized_content(post)

    assert result is not None
    assert result.tags == []


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
