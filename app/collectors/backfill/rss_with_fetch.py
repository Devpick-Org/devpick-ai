"""RSS backfill collector — RSS listing + individual article page fetch.

For feeds that provide only a summary or short snippet in the RSS body.
Fetches each article page individually and extracts full body text.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import requests
from curl_cffi import requests as cffi_requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.collectors.backfill.base import BackfillCollector
from app.schemas.raw_content import RawEntry
from app.schemas.source import SourceConfig
from bs4 import BeautifulSoup

from app.utils.html_helpers import (
    extract_article_body,
    extract_jsonld_field,
    extract_kakao_article_body,
    extract_meta_author,
    extract_og_image,
    html_to_text,
)
from app.utils.xml_helpers import compute_entry_hash, normalize_date, sha256_text

logger = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class RSSWithFetchBackfillCollector(BackfillCollector):
    """Collect articles from an RSS feed and fetch each page for full body.

    For feeds that include only a summary/excerpt rather than the full article HTML.
    Each unseen URL is fetched individually; body is extracted via ``<article>``
    tag first, then falls back to the heuristic selector used by
    ``extract_kakao_article_body``.

    Two phases:

    * **backfill** — collect all unseen articles on or after *since*.
      Transitions to incremental once the feed is exhausted.

    * **incremental** — re-scan the feed each run; collect only unseen entries.
      Never marks ``done: True``.

    Cursor format::

        {"phase": "backfill" | "incremental", "seen_ids": [...]}
    """

    def __init__(
        self,
        since: str = "2026-01-01",
        timeout: float = 15.0,
        max_retries: int = 2,
        user_agent: str = _BROWSER_UA,
        use_cffi: bool = False,
        extra_body_selectors: list[str] | None = None,
    ) -> None:
        self.since = since
        self.timeout = timeout
        self.user_agent = user_agent
        self.use_cffi = use_cffi
        self.extra_body_selectors: list[str] = extra_body_selectors or []

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
        seen_ids: set[str] = set(cursor.get("seen_ids", []))

        feed_entries = self._fetch_feed(source.feed_url)
        if feed_entries is None:
            return [], {**cursor, "phase": phase}

        new_entries: list[RawEntry] = []
        for fe in feed_entries:
            entry_url = fe.get("link", "")
            if not entry_url or entry_url in seen_ids:
                continue

            published_at = self._extract_date(fe)
            if published_at and published_at[:10] < self.since:
                continue

            entry = self._fetch_and_build_entry(source, fe, entry_url, published_at)
            if entry is not None:
                new_entries.append(entry)

        if not new_entries:
            logger.info("%s %s: no new articles", source.name, phase)
            return [], {"phase": "incremental", "seen_ids": list(seen_ids)}

        to_return = new_entries[:batch_size]
        has_more = len(new_entries) > batch_size
        next_phase = "backfill" if has_more else "incremental"

        for e in to_return:
            seen_ids.add(e.entry_external_id)

        logger.info(
            "%s %s: collected %d articles (phase→%s)",
            source.name,
            phase,
            len(to_return),
            next_phase,
        )
        return to_return, {"phase": next_phase, "seen_ids": list(seen_ids)}

    def _fetch_feed(self, feed_url: str) -> list | None:
        try:
            if self.use_cffi:
                resp = cffi_requests.get(
                    feed_url, impersonate="chrome", timeout=self.timeout
                )
            else:
                resp = self.session.get(
                    feed_url,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                )
            resp.raise_for_status()
            raw = resp.text
        except Exception as err:
            logger.warning("RSSWithFetch: feed fetch failed %s: %s", feed_url, err)
            return None

        parsed = feedparser.parse(raw)
        if parsed.bozo and not parsed.entries:
            logger.warning(
                "RSSWithFetch: feed parse error %s: %s",
                feed_url,
                parsed.bozo_exception,
            )
            return None

        logger.info("RSSWithFetch %s: fetched %d entries", feed_url, len(parsed.entries))
        return parsed.entries

    def _fetch_page(self, url: str) -> str | None:
        try:
            if self.use_cffi:
                resp = cffi_requests.get(
                    url, impersonate="chrome", timeout=self.timeout
                )
            else:
                resp = self.session.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                )
            if resp.status_code >= 400:
                logger.warning(
                    "RSSWithFetch: page %s returned %d", url, resp.status_code
                )
                return None
            return resp.text
        except Exception as err:
            logger.warning("RSSWithFetch: page fetch failed %s: %s", url, err)
            return None

    def _fetch_and_build_entry(
        self,
        source: SourceConfig,
        fe: dict,
        entry_url: str,
        published_at: str | None,
    ) -> RawEntry | None:
        title = fe.get("title") or None
        author = fe.get("author") or None
        tags = [t.get("term", "") for t in fe.get("tags", []) if t.get("term")]

        # Thumbnail from feed (media_thumbnail or image enclosure)
        thumbnail_url: str | None = None
        for media in fe.get("media_thumbnail", []):
            thumbnail_url = media.get("url")
            break
        if not thumbnail_url:
            for enc in fe.get("enclosures", []):
                if enc.get("type", "").startswith("image/"):
                    thumbnail_url = enc.get("href")
                    break

        # Feed body fallback if page fetch fails
        feed_html: str | None = None
        for c in fe.get("content", []):
            if c.get("type") in ("text/html", "application/xhtml+xml", "html", ""):
                feed_html = c.get("value")
                break
        if not feed_html:
            feed_html = fe.get("summary") or None

        # Fetch full article page
        page_html = self._fetch_page(entry_url)

        body_html: str | None = None
        body_text: str | None = None

        if page_html:
            # Date fallback: some feeds omit dates — extract from page JSON-LD
            if not published_at:
                raw_date = extract_jsonld_field(page_html, "datePublished")
                if raw_date:
                    published_at = normalize_date(raw_date)

            # 1. Try source-specific selectors first
            body_html = body_text = None
            if self.extra_body_selectors:
                soup = BeautifulSoup(page_html, "html.parser")
                for selector in self.extra_body_selectors:
                    node = soup.select_one(selector)
                    if node:
                        candidate_html = str(node)
                        candidate_text = html_to_text(candidate_html)
                        if candidate_text and len(candidate_text) >= 200:
                            body_html = candidate_html
                            body_text = candidate_text
                            break

            # 2. Try <article> tag
            if not body_html or len(body_text or "") < 200:
                body_html, body_text = extract_article_body(page_html)

            # 3. Fall back to heuristic selector + Nuxt payload extraction
            if not body_html or len(body_text or "") < 200:
                body_html, body_text = extract_kakao_article_body(page_html)

            # OG image from full page is more reliable than feed thumbnail
            og_image = extract_og_image(page_html)
            if og_image:
                thumbnail_url = og_image

            if not author:
                author = extract_meta_author(page_html)
        else:
            # Fall back to feed body if page fetch failed
            body_html = feed_html or ""
            body_text = html_to_text(body_html) if body_html else ""

        response_hash = sha256_text(body_html or feed_html or "")
        entry_hash = compute_entry_hash(
            source_name=source.name,
            entry_external_id=entry_url,
            entry_url=entry_url,
            title_raw=title,
            published_at_raw=published_at,
            summary_raw=None,
            content_raw=None,
        )

        logger.info(
            "%s entry %s title=%s date=%s body_len=%d",
            source.name,
            entry_url.split("/")[-1][:30],
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
            entry_external_id=entry_url,
            entry_url=entry_url,
            title_raw=title,
            author_raw=author,
            published_at_raw=published_at,
            summary_raw=None,
            content_raw=None,
            html_body_raw=body_html if body_html else None,
            html_text_raw=body_text if body_text and len(body_text) > 100 else None,
            thumbnail_url=thumbnail_url,
            categories_raw=tags,
            fetched_at=datetime.now(timezone.utc),
            response_hash=response_hash,
            parser_version="backfill-rss-fetch-v1",
            entry_hash=entry_hash,
        )

    @staticmethod
    def _extract_date(fe: dict) -> str | None:
        raw = fe.get("published") or fe.get("updated") or None
        if not raw:
            return None
        return normalize_date(raw)
