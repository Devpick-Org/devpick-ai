"""Velog GraphQL API collector for Korean developer blog posts.

수집 전략:
- POST https://v2.velog.io/graphql → posts 쿼리로 최신 글 수집
- Origin: https://velog.io 헤더 필수
- ADR-006 정책: SUMMARY_ONLY
  - is_original_visible = False
  - body_candidate = None (short_description만 preview로 저장)
"""

from __future__ import annotations

import logging
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.schemas.normalized_content import NormalizedContent

logger = logging.getLogger(__name__)

_GRAPHQL_URL = "https://v2.velog.io/graphql"
_PREVIEW_MAX_LENGTH = 260
_POSTS_QUERY = """
query Posts {
  posts {
    id
    title
    short_description
    url_slug
    released_at
    tags
    user {
      username
    }
  }
}
"""


class VelogCollector:
    """Collects recent posts from Velog GraphQL API.

    ADR-006 정책: SUMMARY_ONLY
    - is_original_visible = False
    - body_candidate = None (preview만 저장, 원문 미표시)

    Usage:
        collector = VelogCollector()
        contents = collector.fetch()
        # contents: list[NormalizedContent]
    """

    def __init__(
        self,
        timeout: float = 15.0,
        max_retries: int = 2,
    ) -> None:
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
        """Fetch recent posts from Velog GraphQL API.

        Returns:
            List of NormalizedContent for each collected post.
        """
        try:
            posts = self._fetch_posts()
            results = [
                content
                for post in posts
                if (content := self._to_normalized_content(post)) is not None
            ]
            logger.info("Velog collected=%d posts", len(results))
            return results

        except Exception:
            logger.exception("Velog collection failed")
            return []

    def _fetch_posts(self) -> list[dict]:
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
        username = (post.get("user") or {}).get("username") or "Unknown"
        url_slug = post.get("url_slug")

        canonical_url: str | None = None
        if username and url_slug:
            canonical_url = f"https://velog.io/@{username}/{url_slug}"

        published_at: str | None = None
        released_at = post.get("released_at")
        if released_at:
            try:
                dt = datetime.fromisoformat(released_at.replace("Z", "+00:00"))
                published_at = dt.isoformat()
            except (ValueError, AttributeError):
                logger.warning("Failed to parse Velog released_at: %r", released_at)

        preview = post.get("short_description") or None
        if preview and len(preview) > _PREVIEW_MAX_LENGTH:
            preview = preview[:_PREVIEW_MAX_LENGTH]

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
            tags=post.get("tags") or [],
        )
