"""Kakao Tech backfill collector — sequential post ID crawling."""

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
    extract_kakao_article_body_result,
    extract_og_image,
    extract_og_meta,
)
from app.utils.xml_helpers import compute_entry_hash, sha256_text

logger = logging.getLogger(__name__)

# Kakao posts URL pattern: https://tech.kakao.com/posts/{id}
KAKAO_POST_URL = "https://tech.kakao.com/posts/{post_id}"

# Regex to extract metadata from Nuxt payload:
# Pattern: },<id>,"<title>","<date_short>","<date_full>",...,"<author_nickname>"
_NUXT_META_RE = re.compile(
    r"\},(\d+),"  # post ID
    r'"([^"]+)",'  # title
    r'"(\d{4}\.\d{2}\.\d{2})",'  # date (YYYY.MM.DD)
    r'"(\d{4}\.\d{2}\.\d{2}\s[\d:]+)",'  # datetime (YYYY.MM.DD HH:MM:SS)
)

_NUXT_AUTHOR_RE = re.compile(
    r'"blog",\{"name":\d+,"description":\d+,"profile":\d+\},"([^"]+)"'
)

# Max consecutive 404s before assuming end of post range (backfill phase)
MAX_CONSECUTIVE_MISSES = 10
# Max consecutive 404s in incremental phase (fewer = faster checks)
MAX_INCREMENTAL_MISSES = 5


class KakaoBackfillCollector(BackfillCollector):
    """Crawl Kakao Tech posts by sequential ID enumeration.

    Two phases:

    * **backfill** — enumerate IDs from start_id upward, collecting posts
      published on or after *since*.  Transitions to incremental when
      MAX_CONSECUTIVE_MISSES 404s are seen.

    * **incremental** — continues from the last known ID; returns an empty
      batch when MAX_INCREMENTAL_MISSES 404s are seen (means no new posts
      yet).  Never marks ``done: True``.

    Cursor format::

        {"phase": "backfill" | "incremental", "next_id": 683}
    """

    def __init__(
        self,
        start_id: int = 675,
        end_id: int | None = None,
        since: str = "2026-01-01",
        timeout: float = 10.0,
        max_retries: int = 2,
        delay: float = 1.5,
        user_agent: str = "DevPickAI-Backfill/1.0",
    ) -> None:
        self.start_id = start_id
        self.end_id = end_id
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
        next_id = cursor.get("next_id", self.start_id)

        if phase == "incremental":
            return self._collect_incremental(source, next_id, batch_size)
        return self._collect_backfill(source, next_id, batch_size)

    def _collect_backfill(
        self, source: SourceConfig, next_id: int, batch_size: int
    ) -> tuple[list[RawEntry], dict]:
        entries: list[RawEntry] = []
        consecutive_misses = 0
        current_id = next_id

        while len(entries) < batch_size:
            if self.end_id is not None and current_id > self.end_id:
                logger.info("Kakao backfill reached end_id=%d", self.end_id)
                return entries, {"phase": "incremental", "next_id": current_id}

            if consecutive_misses >= MAX_CONSECUTIVE_MISSES:
                logger.info(
                    "Kakao backfill: %d consecutive misses at id=%d — transitioning to incremental",
                    consecutive_misses,
                    current_id,
                )
                return entries, {"phase": "incremental", "next_id": current_id}

            entry = self._fetch_post(source, current_id)
            current_id += 1

            if entry is None:
                consecutive_misses += 1
                continue

            consecutive_misses = 0

            if entry.published_at_raw and entry.published_at_raw < self.since:
                logger.debug(
                    "Kakao post %d published_at=%s before since=%s, skipping",
                    current_id - 1,
                    entry.published_at_raw,
                    self.since,
                )
                continue

            entries.append(entry)
            time.sleep(self.delay)

        return entries, {"phase": "backfill", "next_id": current_id}

    def _collect_incremental(
        self, source: SourceConfig, next_id: int, batch_size: int
    ) -> tuple[list[RawEntry], dict]:
        """Check for new posts above the last known ID."""
        entries: list[RawEntry] = []
        consecutive_misses = 0
        current_id = next_id

        while len(entries) < batch_size:
            if consecutive_misses >= MAX_INCREMENTAL_MISSES:
                logger.info(
                    "Kakao incremental: %d consecutive misses at id=%d — no new posts",
                    consecutive_misses,
                    current_id,
                )
                break

            entry = self._fetch_post(source, current_id)
            current_id += 1

            if entry is None:
                consecutive_misses += 1
                continue

            consecutive_misses = 0
            entries.append(entry)
            time.sleep(self.delay)

        return entries, {"phase": "incremental", "next_id": current_id}

    def _fetch_post(self, source: SourceConfig, post_id: int) -> RawEntry | None:
        """Fetch a single Kakao post page and extract article data."""
        url = KAKAO_POST_URL.format(post_id=post_id)
        headers = {"User-Agent": self.user_agent}

        try:
            response = self.session.get(url, headers=headers, timeout=self.timeout)
        except Exception as error:
            logger.warning("Kakao fetch failed id=%d error=%s", post_id, error)
            return None

        if response.status_code == 404:
            logger.debug("Kakao post %d not found (404)", post_id)
            return None

        if response.status_code != 200:
            logger.warning(
                "Kakao post %d unexpected status=%d", post_id, response.status_code
            )
            return None

        html = response.text

        # Extract metadata from Nuxt payload
        title, published_at, author = self._extract_meta(html, post_id)
        if not title:
            logger.warning("Kakao post %d: no title found, skipping", post_id)
            return None

        # Extract body using existing Kakao extractor
        result = extract_kakao_article_body_result(html)
        body_html = result.body_html
        body_text = result.body_text

        # Extract thumbnail
        thumbnail_url = extract_og_image(html)

        entry_url = url
        entry_external_id = url
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
            "Kakao post %d fetched title=%s date=%s body_len=%d",
            post_id,
            title[:40] if title else "?",
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
            html_text_raw=body_text,
            thumbnail_url=thumbnail_url,
            categories_raw=[],
            fetched_at=datetime.now(timezone.utc),
            response_hash=response_hash,
            parser_version="backfill-kakao-v1",
            entry_hash=entry_hash,
        )

    @staticmethod
    def _extract_meta(
        html: str, post_id: int
    ) -> tuple[str | None, str | None, str | None]:
        """Extract title, published date (ISO), and author from Nuxt payload."""
        title: str | None = None
        published_at: str | None = None
        author: str | None = None

        # Try Nuxt payload regex
        for m in _NUXT_META_RE.finditer(html):
            if int(m.group(1)) == post_id:
                title = m.group(2)
                date_str = m.group(4)  # "2025.01.17 17:25:00"
                try:
                    dt = datetime.strptime(date_str, "%Y.%m.%d %H:%M:%S")
                    dt = dt.replace(tzinfo=timezone.utc)
                    published_at = dt.isoformat()
                except ValueError:
                    published_at = date_str
                break

        # Fallback: og:title
        if not title:
            raw = extract_og_meta(html, "og:title")
            if raw:
                # Remove " - tech.kakao.com" suffix
                title = re.sub(r"\s*-\s*tech\.kakao\.com$", "", raw).strip() or None

        # Author from Nuxt payload
        author_match = _NUXT_AUTHOR_RE.search(html)
        if author_match:
            author = author_match.group(1)

        return title, published_at, author
