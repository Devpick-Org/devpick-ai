"""Velog backfill + incremental collector.

수집 전략:
- backfill phase: trendingPosts(timeframe="year") → 빈 배열이면 크롤링
  - released_at >= 2026-01-01 필터링
  - 완료 후 → incremental phase 전환
- incremental phase: trendingPosts(timeframe="week") → 빈 배열이면 크롤링

크롤링 전략 (GraphQL 빈 배열 시):
- GET https://velog.io/trending
- __NEXT_DATA__ JSON 추출 시도
- 실패 시 HTML 파싱으로 포스트 카드 추출

커서 형식:
  backfill:    {"phase": "backfill", "fetched": false}
  incremental: {"phase": "incremental"}

본문 수집 전략:
- trendingPosts 수집 후 각 포스트에 대해 post(input) GraphQL로 markdown 본문 개별 fetch
- body_candidate = markdown 본문 (AI 요약에 사용)
- is_original_visible = True
- 본문 fetch 실패 시 해당 포스트는 body_candidate=None으로 저장 (요약 스킵)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.schemas.normalized_content import NormalizedContent

logger = logging.getLogger(__name__)

_GRAPHQL_URL = "https://v3.velog.io/graphql"
_TRENDING_URL = "https://velog.io/trending"
_PREVIEW_MAX_LENGTH = 260
_DEFAULT_MIN_DATE = "2026-01-01"
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

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

_POST_BODY_QUERY = """
query GetPost($input: ReadPostInput!) {
  post(input: $input) {
    body
  }
}
"""


class VelogBackfillCollector:
    """Monthly backfill + incremental trending collector for Velog.

    BackfillCollector 인터페이스를 따르지 않고 NormalizedContent를 직접 반환한다.
    run_backfill_batch.py의 _DIRECT_COLLECTOR_FACTORIES에 등록해서 사용한다.

    Usage:
        collector = VelogBackfillCollector(min_date="2026-01-01")
        items, new_cursor = collector.collect_batch_normalized(cursor, batch_size=20)
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
            allowed_methods=frozenset(["GET", "POST"]),
            backoff_factor=1.0,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def collect_batch_normalized(
        self, cursor: dict, batch_size: int = 20
    ) -> tuple[list[NormalizedContent], dict]:
        """Collect one batch and return (items, updated_cursor)."""
        phase = cursor.get("phase", "backfill")

        if phase == "backfill":
            return self._collect_backfill(cursor, batch_size)
        else:
            items = self._fetch_incremental(batch_size)
            return items, cursor

    # ------------------------------------------------------------------
    # backfill: year timeframe → crawl fallback
    # ------------------------------------------------------------------

    def _collect_backfill(
        self, cursor: dict, batch_size: int
    ) -> tuple[list[NormalizedContent], dict]:
        # year timeframe로 넓은 범위 수집
        posts = self._fetch_graphql(timeframe="year", limit=batch_size)

        if not posts:
            logger.info("Velog backfill: GraphQL empty, falling back to crawl")
            posts = self._crawl_trending(batch_size)

        posts = self._enrich_with_body(posts)
        items = [
            c for post in posts if (c := self._to_normalized_content(post)) is not None
        ]

        logger.info(
            "Velog backfill collected=%d (min_date=%s)", len(items), self.min_date
        )
        return items, {"phase": "incremental"}

    # ------------------------------------------------------------------
    # incremental: week timeframe → crawl fallback
    # ------------------------------------------------------------------

    def _fetch_incremental(self, batch_size: int) -> list[NormalizedContent]:
        posts = self._fetch_graphql(timeframe="week", limit=batch_size)

        if not posts:
            logger.info("Velog incremental: GraphQL empty, falling back to crawl")
            posts = self._crawl_trending(batch_size)

        posts = self._enrich_with_body(posts)
        items = [
            c for post in posts if (c := self._to_normalized_content(post)) is not None
        ]
        logger.info("Velog incremental collected=%d", len(items))
        return items

    # ------------------------------------------------------------------
    # GraphQL 호출
    # ------------------------------------------------------------------

    def _fetch_post_body(self, username: str, url_slug: str) -> str | None:
        """Fetch full markdown body for a single post via GraphQL."""
        payload = {
            "operationName": "GetPost",
            "query": _POST_BODY_QUERY,
            "variables": {"input": {"username": username, "url_slug": url_slug}},
        }
        try:
            resp = self.session.post(
                _GRAPHQL_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://velog.io",
                    "User-Agent": _DEFAULT_USER_AGENT,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            body = (resp.json().get("data") or {}).get("post", {}).get("body")
            return body or None
        except Exception:
            logger.warning(
                "Velog post body fetch failed: @%s/%s",
                username,
                url_slug,
                exc_info=True,
            )
            return None

    def _enrich_with_body(self, posts: list[dict]) -> list[dict]:
        """Fetch and inject body into each post dict."""
        enriched = []
        for post in posts:
            username = (post.get("user") or {}).get("username") or ""
            url_slug = post.get("url_slug") or ""
            if username and url_slug:
                body = self._fetch_post_body(username, url_slug)
                post = {**post, "_body": body}
            enriched.append(post)
        return enriched

    def _fetch_graphql(self, timeframe: str, limit: int) -> list[dict]:
        payload = {
            "operationName": "TrendingPosts",
            "query": _TRENDING_QUERY,
            "variables": {
                "input": {"limit": limit, "offset": 0, "timeframe": timeframe}
            },
        }
        try:
            resp = self.session.post(
                _GRAPHQL_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://velog.io",
                    "User-Agent": _DEFAULT_USER_AGENT,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            posts = (data.get("data") or {}).get("trendingPosts") or []
            logger.info(
                "Velog GraphQL trendingPosts(timeframe=%s): %d posts",
                timeframe,
                len(posts),
            )
            return posts
        except Exception:
            logger.warning(
                "Velog GraphQL failed (timeframe=%s)", timeframe, exc_info=True
            )
            return []

    # ------------------------------------------------------------------
    # HTML 크롤링 fallback
    # ------------------------------------------------------------------

    def _crawl_trending(self, limit: int) -> list[dict]:
        """Crawl https://velog.io/trending and extract post data.

        1. __NEXT_DATA__ JSON 추출 시도
        2. 실패 시 HTML 정규식 파싱
        """
        try:
            resp = self.session.get(
                _TRENDING_URL,
                headers={"User-Agent": _DEFAULT_USER_AGENT},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            html = resp.text

            # 1. __NEXT_DATA__ 시도
            posts = self._extract_from_next_data(html, limit)
            if posts:
                logger.info("Velog crawl via __NEXT_DATA__: %d posts", len(posts))
                return posts

            # 2. HTML 정규식 파싱
            posts = self._extract_from_html(html, limit)
            logger.info("Velog crawl via HTML regex: %d posts", len(posts))
            return posts

        except Exception:
            logger.exception("Velog crawl failed")
            return []

    def _extract_from_next_data(self, html: str, limit: int) -> list[dict]:
        """Extract posts from Next.js __NEXT_DATA__ script tag."""
        match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>',
            html,
            re.DOTALL,
        )
        if not match:
            return []

        try:
            next_data = json.loads(match.group(1))
            # Velog Next.js 구조: props.pageProps.data 또는 dehydratedState 내부
            page_props = next_data.get("props", {}).get("pageProps", {})

            # 경로 1: pageProps.posts
            raw_posts = page_props.get("posts") or []

            # 경로 2: dehydratedState queries 내부
            if not raw_posts:
                queries = page_props.get("dehydratedState", {}).get("queries", [])
                for query in queries:
                    data = query.get("state", {}).get("data", {})
                    if isinstance(data, dict):
                        raw_posts = data.get("trendingPosts") or data.get("posts") or []
                    if raw_posts:
                        break

            return raw_posts[:limit]
        except (json.JSONDecodeError, AttributeError, KeyError):
            return []

    def _extract_from_html(self, html: str, limit: int) -> list[dict]:
        """Extract post metadata from rendered HTML as fallback."""
        posts: list[dict] = []

        # 포스트 카드 URL 패턴: /@username/slug
        urls = re.findall(r'href="(/@[^/]+/[^"?]+)"', html)
        titles = re.findall(r'class="[^"]*title[^"]*"[^>]*>([^<]+)</[^>]+>', html)

        seen_urls: set[str] = set()
        for i, url in enumerate(urls):
            if url in seen_urls or not url.startswith("/@"):
                continue
            seen_urls.add(url)

            parts = url.lstrip("/").split("/")
            if len(parts) < 2:
                continue

            username = parts[0].lstrip("@")
            url_slug = "/".join(parts[1:])
            title = titles[i] if i < len(titles) else url_slug.replace("-", " ")

            posts.append(
                {
                    "id": url,
                    "title": title.strip(),
                    "short_description": None,
                    "url_slug": url_slug,
                    "released_at": None,
                    "tags": [],
                    "likes": None,
                    "comments_count": None,
                    "user": {"username": username},
                }
            )
            if len(posts) >= limit:
                break

        return posts

    # ------------------------------------------------------------------
    # NormalizedContent 변환
    # ------------------------------------------------------------------

    def _to_normalized_content(self, post: dict) -> NormalizedContent | None:
        released_at = post.get("released_at")
        published_at: str | None = None

        if released_at:
            try:
                dt = datetime.fromisoformat(released_at.replace("Z", "+00:00"))
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

        if not canonical_url:
            return None

        preview = post.get("short_description") or None
        if preview and len(preview) > _PREVIEW_MAX_LENGTH:
            preview = preview[:_PREVIEW_MAX_LENGTH]

        tags: list[str] = post.get("tags") or []

        likes_raw = post.get("likes")
        likes = int(likes_raw) if likes_raw is not None else None

        comments_raw = post.get("comments_count")
        comments_count = int(comments_raw) if comments_raw is not None else None

        body_candidate: str | None = post.get("_body")

        return NormalizedContent(
            source_name="Velog",
            title=post.get("title"),
            author=username,
            canonical_url=canonical_url,
            published_at=published_at,
            preview=preview,
            body_candidate=body_candidate,
            is_original_visible=True,
            license_type=None,
            tags=tags,
            likes=likes,
            comments_count=comments_count,
        )


def _parse_min_date(min_date_str: str) -> datetime | None:
    if not min_date_str:
        return None
    try:
        return datetime.fromisoformat(min_date_str).replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        logger.warning(
            "Failed to parse VELOG_MIN_DATE: %r, no date filter applied", min_date_str
        )
        return None
