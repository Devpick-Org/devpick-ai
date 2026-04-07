"""Naver D2 backfill collector — REST API pagination + individual article fetch."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.collectors.backfill.base import BackfillCollector
from app.schemas.raw_content import RawEntry
from app.schemas.source import SourceConfig
from app.utils.html_helpers import html_to_text
from app.utils.xml_helpers import compute_entry_hash, sha256_text

logger = logging.getLogger(__name__)

D2_API_BASE = "https://d2.naver.com"
D2_LIST_URL = f"{D2_API_BASE}/api/v1/contents"
D2_DETAIL_URL = f"{D2_API_BASE}/api/v1/contents/{{content_id}}"


class NaverD2BackfillCollector(BackfillCollector):
    """Crawl Naver D2 articles via internal REST API.

    Two-step process per batch:
    1. Paginate listing API to discover article IDs and dates.
    2. Fetch individual article API for full body HTML.

    Two phases:

    * **backfill** — paginate newest-first until timestamp < since_ts.
      Transitions to incremental once exhausted.

    * **incremental** — re-fetches page 0 each run, collecting only articles
      newer than ``latest_seen_ts``.  Never marks ``done: True``.

    Cursor format::

        {"phase": "backfill",     "next_page": 0, "pending_ids": [], "latest_seen_ts": 0}
        {"phase": "incremental",  "latest_seen_ts": 1735689600000}
    """

    def __init__(
        self,
        since: str = "2026-01-01",
        timeout: float = 10.0,
        max_retries: int = 2,
        delay: float = 1.5,
        user_agent: str = "DevPickAI-Backfill/1.0",
    ) -> None:
        self.since = since
        self.since_ts = int(
            datetime.strptime(since, "%Y-%m-%d")
            .replace(tzinfo=timezone.utc)
            .timestamp()
            * 1000
        )
        self.timeout = timeout
        self.delay = delay
        self.user_agent = user_agent

        self.session = requests.Session()
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET"]),
            backoff_factor=0.5,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def collect_batch(
        self, source: SourceConfig, cursor: dict, batch_size: int = 20
    ) -> tuple[list[RawEntry], dict]:
        phase = self._resolve_phase(cursor)

        if phase == "incremental":
            return self._collect_incremental(source, cursor, batch_size)
        return self._collect_backfill(source, cursor, batch_size)

    # ------------------------------------------------------------------
    # Backfill phase
    # ------------------------------------------------------------------

    def _collect_backfill(
        self, source: SourceConfig, cursor: dict, batch_size: int
    ) -> tuple[list[RawEntry], dict]:
        next_page = cursor.get("next_page", 0)
        pending_ids: list[int] = cursor.get("pending_ids", [])
        latest_seen_ts: int = cursor.get("latest_seen_ts", 0)

        # If no pending IDs, load next listing page(s) until we have some
        exhausted = False
        if not pending_ids:
            pending_ids, next_page, exhausted = self._load_pending_ids(next_page)
            if not pending_ids:
                logger.info(
                    "Naver D2 backfill: no more articles — transitioning to incremental"
                )
                return [], {
                    "phase": "incremental",
                    "latest_seen_ts": latest_seen_ts,
                }

        # Fetch up to batch_size articles from pending_ids
        to_fetch = pending_ids[:batch_size]
        remaining = pending_ids[batch_size:]

        entries: list[RawEntry] = []
        for content_id in to_fetch:
            entry = self._fetch_article(source, content_id)
            if entry is not None:
                entries.append(entry)
                # Track the highest timestamp seen
                if entry.published_at_raw:
                    try:
                        ts = int(
                            datetime.fromisoformat(entry.published_at_raw).timestamp()
                            * 1000
                        )
                        if ts > latest_seen_ts:
                            latest_seen_ts = ts
                    except (ValueError, OSError):
                        pass
            time.sleep(self.delay)

        # If this was the last page (exhausted) and no more pending, go incremental
        if exhausted and not remaining:
            logger.info(
                "Naver D2 backfill: last page exhausted — transitioning to incremental"
            )
            return entries, {
                "phase": "incremental",
                "latest_seen_ts": latest_seen_ts,
            }

        new_cursor: dict = {
            "phase": "backfill",
            "next_page": next_page,
            "pending_ids": remaining,
            "latest_seen_ts": latest_seen_ts,
        }
        return entries, new_cursor

    def _load_pending_ids(self, start_page: int) -> tuple[list[int], int, bool]:
        """Load listing pages to collect article IDs published after *since*.

        Returns (ids, next_page, exhausted).
        """
        pending: list[int] = []
        page = start_page
        exhausted = False

        while not pending:
            items, has_next = self._fetch_listing_page(page)
            if not items:
                exhausted = True
                break

            for item in items:
                ts = item.get("postPublishedAt", 0)
                if ts >= self.since_ts:
                    url_path = item.get("url", "")
                    content_id = self._extract_content_id(url_path)
                    if content_id is not None:
                        pending.append(content_id)
                elif ts < self.since_ts:
                    exhausted = True
                    break

            if exhausted:
                break

            page += 1
            if not has_next:
                exhausted = True
                break

            time.sleep(self.delay)

        return pending, page + (1 if not exhausted else 0), exhausted

    # ------------------------------------------------------------------
    # Incremental phase
    # ------------------------------------------------------------------

    def _collect_incremental(
        self, source: SourceConfig, cursor: dict, batch_size: int
    ) -> tuple[list[RawEntry], dict]:
        """Fetch page 0 of the listing API and collect articles newer than latest_seen_ts."""
        latest_seen_ts: int = cursor.get("latest_seen_ts", self.since_ts)

        items, _ = self._fetch_listing_page(0)
        new_ids: list[int] = []
        new_latest_ts = latest_seen_ts

        for item in items:
            ts = item.get("postPublishedAt", 0)
            if ts > latest_seen_ts:
                url_path = item.get("url", "")
                content_id = self._extract_content_id(url_path)
                if content_id is not None:
                    new_ids.append(content_id)
                if ts > new_latest_ts:
                    new_latest_ts = ts
            else:
                # Listing is newest-first; stop once we see known articles
                break

        if not new_ids:
            logger.info("Naver D2 incremental: no new articles")
            return [], {"phase": "incremental", "latest_seen_ts": latest_seen_ts}

        to_fetch = new_ids[:batch_size]
        entries: list[RawEntry] = []
        for content_id in to_fetch:
            entry = self._fetch_article(source, content_id)
            if entry is not None:
                entries.append(entry)
            time.sleep(self.delay)

        logger.info("Naver D2 incremental: found %d new articles", len(entries))
        return entries, {"phase": "incremental", "latest_seen_ts": new_latest_ts}

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _fetch_listing_page(self, page: int) -> tuple[list[dict], bool]:
        """Fetch one page of the listing API."""
        headers = {"User-Agent": self.user_agent}
        params = {"page": page, "size": 20}

        try:
            response = self.session.get(
                D2_LIST_URL, headers=headers, params=params, timeout=self.timeout
            )
            response.raise_for_status()
        except Exception as error:
            logger.warning("D2 listing page=%d failed: %s", page, error)
            return [], False

        data = response.json()
        items = data.get("content", [])
        links = {link["rel"]: link for link in data.get("links", [])}
        has_next = "next" in links

        logger.info(
            "D2 listing page=%d items=%d has_next=%s", page, len(items), has_next
        )
        return items, has_next

    @staticmethod
    def _extract_content_id(url_path: str) -> int | None:
        """Extract numeric content ID from a D2 URL path like '/helloworld/7997284'."""
        m = re.search(r"/(\d+)$", url_path)
        return int(m.group(1)) if m else None

    def _fetch_article(self, source: SourceConfig, content_id: int) -> RawEntry | None:
        """Fetch full article detail from individual API."""
        url = D2_DETAIL_URL.format(content_id=content_id)
        headers = {"User-Agent": self.user_agent}

        try:
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except Exception as error:
            logger.warning("D2 article id=%d failed: %s", content_id, error)
            return None

        data = response.json()

        title = data.get("postTitle")
        post_html = data.get("postHtml", "")
        post_ts = data.get("postPublishedAt", 0)
        article_url_path = data.get("url", "")
        authors_data = data.get("authors", [])
        thumbnail_path = data.get("postImage")
        raw_tags = data.get("postTags") or []
        tags = [t["name"] if isinstance(t, dict) else str(t) for t in raw_tags if t]

        # Build full URL
        entry_url = f"{D2_API_BASE}{article_url_path}" if article_url_path else None
        entry_external_id = entry_url or f"d2-{content_id}"

        # Parse timestamp
        published_at: str | None = None
        if post_ts:
            try:
                dt = datetime.fromtimestamp(post_ts / 1000, tz=timezone.utc)
                published_at = dt.isoformat()
            except (OSError, ValueError):
                published_at = str(post_ts)

        # Author names
        author_names = [a.get("name", "") for a in authors_data if a.get("name")]
        author = ", ".join(author_names) if author_names else None

        # Thumbnail URL
        thumbnail_url = None
        if thumbnail_path:
            thumbnail_url = (
                f"{D2_API_BASE}{thumbnail_path}"
                if thumbnail_path.startswith("/")
                else thumbnail_path
            )

        body_text = html_to_text(post_html) or ""

        response_hash = sha256_text(post_html)
        entry_hash = compute_entry_hash(
            source_name=source.name,
            entry_external_id=entry_external_id,
            entry_url=entry_url,
            title_raw=title,
            published_at_raw=published_at,
            summary_raw=None,
            content_raw=None,
        )

        logger.info(
            "D2 article id=%d title=%s date=%s body_len=%d",
            content_id,
            (title or "?")[:40],
            published_at or "?",
            len(body_text),
        )

        return RawEntry(
            source_name=source.name,
            feed_url=source.feed_url,
            site_url=source.site_url,
            parser_type="backfill",
            content_level_hint=1,
            entry_external_id=entry_external_id,
            entry_url=entry_url,
            title_raw=title,
            author_raw=author,
            published_at_raw=published_at,
            summary_raw=None,
            content_raw=None,
            html_body_raw=post_html,
            html_text_raw=body_text if len(body_text) > 100 else None,
            thumbnail_url=thumbnail_url,
            categories_raw=tags if isinstance(tags, list) else [],
            fetched_at=datetime.now(timezone.utc),
            response_hash=response_hash,
            parser_version="backfill-d2-v1",
            entry_hash=entry_hash,
        )
