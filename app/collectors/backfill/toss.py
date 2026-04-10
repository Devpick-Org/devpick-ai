"""Toss Tech backfill collector — listing page pagination + article body extraction."""

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
from app.utils.html_helpers import (
    extract_article_body,
    extract_og_image,
    extract_og_image_dimensions,
    extract_og_meta,
)
from app.utils.xml_helpers import compute_entry_hash, sha256_text

logger = logging.getLogger(__name__)

TOSS_BASE = "https://toss.tech"
TOSS_LIST_URL = TOSS_BASE  # pagination via ?page=N

# Repeated/featured articles appear on every page; these are identified by href
_ARTICLE_HREF_RE = re.compile(r'href="(/article/[^"]+)"')

# Extract date from article text: "2026년 4월 1일"
_DATE_RE = re.compile(r"(\d{4})\ub144\s*(\d{1,2})\uc6d4\s*(\d{1,2})\uc77c")


class TossBackfillCollector(BackfillCollector):
    """Crawl Toss Tech articles by paginating the listing page.

    Two phases:

    * **backfill** — paginate toss.tech/?page=N newest-first, collecting all
      articles until discovery yields no new slugs.  Transitions to incremental
      when exhausted.

    * **incremental** — re-fetches page 1 each run, stopping at already-known
      slugs.  Never marks ``done: True``.

    Cursor format::

        {"phase": "backfill",    "next_page": 5, "pending_slugs": [...], "seen_slugs": [...]}
        {"phase": "incremental", "seen_slugs": [...]}
    """

    def __init__(
        self,
        since: str = "2026-01-01",
        timeout: float = 10.0,
        max_retries: int = 2,
        delay: float = 2.0,
        user_agent: str = "DevPickAI-Backfill/1.0",
    ) -> None:
        self.since = since
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
        next_page = cursor.get("next_page", 1)
        pending_slugs: list[str] = cursor.get("pending_slugs", [])
        seen_slugs: set[str] = set(cursor.get("seen_slugs", []))

        if not pending_slugs:
            pending_slugs, next_page, seen_slugs = self._discover_slugs(
                next_page, seen_slugs
            )
            if not pending_slugs:
                logger.info(
                    "Toss backfill: no more articles — transitioning to incremental"
                )
                return [], {
                    "phase": "incremental",
                    "seen_slugs": list(seen_slugs),
                }

        to_fetch = pending_slugs[:batch_size]
        remaining = pending_slugs[batch_size:]

        entries: list[RawEntry] = []
        exhausted = False
        for slug in to_fetch:
            entry = self._fetch_article(source, slug)
            if entry is not None:
                if entry.published_at_raw and entry.published_at_raw < self.since:
                    logger.info(
                        "Toss article %s dated %s before since=%s — backfill exhausted",
                        slug,
                        entry.published_at_raw,
                        self.since,
                    )
                    exhausted = True
                    break
                else:
                    entries.append(entry)
            time.sleep(self.delay)

        if exhausted:
            return entries, {
                "phase": "incremental",
                "seen_slugs": list(seen_slugs),
            }

        new_cursor = {
            "phase": "backfill",
            "next_page": next_page,
            "pending_slugs": remaining,
            "seen_slugs": list(seen_slugs),
        }
        return entries, new_cursor

    def _discover_slugs(
        self, start_page: int, seen: set[str]
    ) -> tuple[list[str], int, set[str]]:
        """Load listing pages to discover new article slugs."""
        new_slugs: list[str] = []
        page = start_page
        max_empty_pages = 2

        empty_streak = 0
        while len(new_slugs) < 40:
            page_slugs = self._fetch_listing_page(page)
            if not page_slugs:
                break

            found_new = False
            for slug in page_slugs:
                if slug not in seen:
                    seen.add(slug)
                    new_slugs.append(slug)
                    found_new = True

            if not found_new:
                empty_streak += 1
                if empty_streak >= max_empty_pages:
                    logger.info(
                        "Toss listing: %d empty pages, stopping discovery", empty_streak
                    )
                    break
            else:
                empty_streak = 0

            page += 1
            time.sleep(self.delay)

        return new_slugs, page, seen

    # ------------------------------------------------------------------
    # Incremental phase
    # ------------------------------------------------------------------

    def _collect_incremental(
        self, source: SourceConfig, cursor: dict, batch_size: int
    ) -> tuple[list[RawEntry], dict]:
        """Check page 1 for new slugs not in seen_slugs."""
        seen_slugs: set[str] = set(cursor.get("seen_slugs", []))

        page_slugs = self._fetch_listing_page(1)
        new_slugs = [s for s in page_slugs if s not in seen_slugs]

        if not new_slugs:
            logger.info("Toss incremental: no new articles")
            return [], {"phase": "incremental", "seen_slugs": list(seen_slugs)}

        to_fetch = new_slugs[:batch_size]
        entries: list[RawEntry] = []
        for slug in to_fetch:
            entry = self._fetch_article(source, slug)
            if entry is not None:
                entries.append(entry)
                seen_slugs.add(slug)
            time.sleep(self.delay)

        logger.info("Toss incremental: found %d new articles", len(entries))
        return entries, {"phase": "incremental", "seen_slugs": list(seen_slugs)}

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _fetch_listing_page(self, page: int) -> list[str]:
        """Fetch one listing page and extract article slugs."""
        headers = {"User-Agent": self.user_agent}
        params = {"page": page}

        try:
            response = self.session.get(
                TOSS_LIST_URL, headers=headers, params=params, timeout=self.timeout
            )
            response.raise_for_status()
        except Exception as error:
            logger.warning("Toss listing page=%d failed: %s", page, error)
            return []

        slugs = _ARTICLE_HREF_RE.findall(response.text)
        result = []
        for href in slugs:
            slug = href.replace("/article/", "")
            if slug:
                result.append(slug)

        logger.info("Toss listing page=%d found %d article refs", page, len(result))
        return result

    def _fetch_article(self, source: SourceConfig, slug: str) -> RawEntry | None:
        """Fetch a Toss article page and extract content."""
        url = f"{TOSS_BASE}/article/{slug}"
        headers = {"User-Agent": self.user_agent}

        try:
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except Exception as error:
            logger.warning("Toss article %s failed: %s", slug, error)
            return None

        html = response.text

        title = extract_og_meta(html, "og:title")
        body_html, body_text = extract_article_body(html)
        published_at = self._extract_date(html)
        author = self._extract_author(body_text or "", title)
        thumbnail_url = extract_og_image(html)
        thumbnail_width, thumbnail_height = extract_og_image_dimensions(html)

        entry_url = url
        canonical = extract_og_meta(html, "og:url")
        entry_external_id = canonical or url
        response_hash = sha256_text(html)
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
            "Toss article %s title=%s date=%s body_len=%d",
            slug,
            (title or "?")[:40],
            published_at or "?",
            len(body_text or ""),
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
            html_body_raw=body_html,
            html_text_raw=body_text if body_text and len(body_text) > 100 else None,
            thumbnail_url=thumbnail_url,
            thumbnail_width=thumbnail_width,
            thumbnail_height=thumbnail_height,
            categories_raw=[],
            fetched_at=datetime.now(timezone.utc),
            response_hash=response_hash,
            parser_version="backfill-toss-v1",
            entry_hash=entry_hash,
        )

    @staticmethod
    def _extract_date(html: str) -> str | None:
        """Extract first Korean date pattern (YYYY년 M월 D일) and convert to ISO."""
        m = _DATE_RE.search(html)
        if not m:
            return None
        try:
            dt = datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                tzinfo=timezone.utc,
            )
            return dt.isoformat()
        except ValueError:
            return None

    @staticmethod
    def _extract_author(body_text: str, title: str | None) -> str | None:
        """Extract author name from article body text."""
        m = re.search(
            r"([\uac00-\ud7a3]{2,5})\s*(?:\xb7|\u00b7|·)\s*[^\n]{3,40}", body_text
        )
        if m:
            return m.group(1)

        m = re.search(r"([\uac00-\ud7a3]{2,5})\s+\d{4}\ub144", body_text)
        return m.group(1) if m else None
