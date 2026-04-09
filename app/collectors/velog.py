"""Velog GraphQL API collector for Korean developer blog posts.

수집 전략:
- trendingPosts 쿼리 먼저 시도 (timeframe="week")
  → 빈 배열이면 posts 쿼리로 fallback (Velog SSR 전환 이후 이슈)
- POST https://v3.velog.io/graphql, Origin: https://velog.io 헤더 필수
- released_at >= VELOG_MIN_DATE (기본값 2026-01-01) 필터링
- ADR-006 정책: SUMMARY_ONLY
  - is_original_visible = False
  - body_candidate = None (short_description만 preview로 저장)
- likes, comments_count 수집 (NormalizedContent 확장 필드)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.schemas.normalized_content import NormalizedContent

logger = logging.getLogger(__name__)

_GRAPHQL_URL = "https://v3.velog.io/graphql"
_PREVIEW_MAX_LENGTH = 260
_DEFAULT_MIN_DATE = "2026-01-01"

# trendingPosts 쿼리 (timeframe=week, 최대 30개)
_TRENDING_QUERY = """
query TrendingPosts($input: TrendingPostsInput!) {
  trendingPosts(input: $input) {
    id
    title
    short_description
    url_slug
    released_at
    tags
    likes
    comments_count
    user {
      username
    }
  }
}
"""

# posts 쿼리 (fallback)
_POSTS_QUERY = """
query Posts {
  posts {
    id
    title
    short_description
    url_slug
    released_at
    tags
    likes
    comments_count
    user {
      username
    }
  }
}
"""


class VelogCollector:
    """Collects trending Korean developer posts from Velog GraphQL API.

    수집 전략:
    1. trendingPosts(timeframe="week") 쿼리 시도
    2. 빈 배열 반환 시 posts 쿼리로 fallback
    3. released_at >= min_date 필터링 (기본값 2026-01-01)

    ADR-006 정책: SUMMARY_ONLY
    - is_original_visible = False
    - body_candidate = None (preview만 저장, 원문 미표시)

    Usage:
        collector = VelogCollector(min_date="2026-01-01")
        contents = collector.fetch()
        # contents: list[NormalizedContent]
    """

    def __init__(
        self,
        min_date: str = _DEFAULT_MIN_DATE,
        timeout: float = 15.0,
        max_retries: int = 2,
    ) -> None:
        self.min_date = min_date
        self._min_datetime = _parse_min_date(min_date)
        self.timeout = timeout
        self.session = requests.Session()

        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["POST"]),
            backoff_factor=1.0,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def fetch(self) -> list[NormalizedContent]:
        """Fetch trending posts from Velog GraphQL API.

        trendingPosts 시도 → 빈 배열이면 posts fallback → min_date 필터링.

        Returns:
            List of NormalizedContent for each collected post.
        """
        try:
            posts = self._fetch_trending_posts()

            if not posts:
                logger.info(
                    "Velog trendingPosts returned empty, falling back to posts query"
                )
                posts = self._fetch_posts()

            results = [
                content
                for post in posts
                if (content := self._to_normalized_content(post)) is not None
            ]
            logger.info(
                "Velog collected=%d posts (min_date=%s, total_fetched=%d)",
                len(results),
                self.min_date,
                len(posts),
            )
            return results

        except Exception:
            logger.exception("Velog collection failed")
            return []

    def _fetch_trending_posts(self) -> list[dict]:
        """Try trendingPosts query with timeframe=week."""
        payload = {
            "operationName": "TrendingPosts",
            "query": _TRENDING_QUERY,
            "variables": {"input": {"limit": 30, "offset": 0, "timeframe": "week"}},
        }
        try:
            resp = self.session.post(
                _GRAPHQL_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://velog.io",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return (data.get("data") or {}).get("trendingPosts") or []
        except Exception:
            logger.warning(
                "Velog trendingPosts query failed, will fallback", exc_info=True
            )
            return []

    def _fetch_posts(self) -> list[dict]:
        """Fallback: posts query (recent posts)."""
        payload = {
            "operationName": "Posts",
            "query": _POSTS_QUERY,
            "variables": None,
        }
        resp = self.session.post(
            _GRAPHQL_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://velog.io",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("data") or {}).get("posts") or []

    def _to_normalized_content(self, post: dict) -> NormalizedContent | None:
        # released_at 파싱 & min_date 필터링
        released_at = post.get("released_at")
        published_at: str | None = None
        if released_at:
            try:
                dt = datetime.fromisoformat(released_at.replace("Z", "+00:00"))
                # min_date 미만이면 제외
                if self._min_datetime and dt < self._min_datetime:
                    return None
                published_at = dt.isoformat()
            except (ValueError, AttributeError):
                logger.warning("Failed to parse Velog released_at: %r", released_at)

        username = (post.get("user") or {}).get("username") or "Unknown"
        url_slug = post.get("url_slug")

        canonical_url: str | None = None
        if username and url_slug:
            canonical_url = f"https://velog.io/@{username}/{url_slug}"

        preview = post.get("short_description") or None
        if preview and len(preview) > _PREVIEW_MAX_LENGTH:
            preview = preview[:_PREVIEW_MAX_LENGTH]

        likes_raw = post.get("likes")
        likes = int(likes_raw) if likes_raw is not None else None

        comments_raw = post.get("comments_count")
        comments_count = int(comments_raw) if comments_raw is not None else None

        return NormalizedContent(
            source_name="Velog",
            title=post.get("title"),
            author=username,
            canonical_url=canonical_url,
            published_at=published_at,
            preview=preview,
            body_candidate=None,  # ADR-006: SUMMARY_ONLY
            is_original_visible=False,
            license_type=None,
            likes=likes,
            comments_count=comments_count,
        )


def _parse_min_date(min_date_str: str) -> datetime | None:
    """Parse YYYY-MM-DD string to timezone-aware datetime (UTC midnight)."""
    if not min_date_str:
        return None
    try:
        return datetime.fromisoformat(min_date_str).replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        logger.warning(
            "Failed to parse VELOG_MIN_DATE: %r, no date filter applied", min_date_str
        )
        return None
