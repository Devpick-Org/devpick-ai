"""OliveYoung Tech backfill collector — RSS feed parsing (full body in feed)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.collectors.backfill.base import BackfillCollector
from app.schemas.raw_content import RawEntry
from app.schemas.source import SourceConfig
from app.utils.html_helpers import html_to_text
from app.utils.xml_helpers import compute_entry_hash, normalize_date, sha256_text

logger = logging.getLogger(__name__)

OLIVEYOUNG_RSS = "https://oliveyoung.tech/rss.xml"


class OliveYoungBackfillCollector(BackfillCollector):
    """Collect OliveYoung Tech articles by parsing the RSS feed.

    OliveYoung's RSS feed includes the full article HTML body in
    ``<content:encoded>``.  No individual page fetching is required.

    Two phases:

    * **backfill** — parse the RSS feed, collect all articles published on or
      after *since* that haven't been seen yet.  Transitions to incremental
      once the feed has been fully processed.

    * **incremental** — re-parse the feed each run and collect any entries
      not already in ``seen_ids``.  Never marks ``done: True``.

    Cursor format::

        {"phase": "backfill" | "incremental", "seen_ids": [...]}
    """

    def __init__(
        self,
        since: str = "2026-01-01",
        timeout: float = 10.0,
        max_retries: int = 2,
        user_agent: str = "DevPickAI-Backfill/1.0",
    ) -> None:
        self.since = since
        self.timeout = timeout
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
        seen_ids: set[str] = set(cursor.get("seen_ids", []))

        feed_entries = self._fetch_feed()
        if feed_entries is None:
            return [], {**cursor, "phase": phase}

        # Collect entries not yet seen and published on/after since
        new_entries: list[RawEntry] = []
        for fe in feed_entries:
            entry_url = fe.get("link", "")
            if not entry_url or entry_url in seen_ids:
                continue

            published_at = self._extract_date(fe)
            if published_at and published_at[:10] < self.since:
                continue

            entry = self._build_entry(source, fe, entry_url, published_at)
            if entry is not None:
                new_entries.append(entry)

        if not new_entries:
            logger.info("OliveYoung %s: no new articles", phase)
            # Backfill complete → transition to incremental
            return [], {"phase": "incremental", "seen_ids": list(seen_ids)}

        # Respect batch_size — only mark returned entries as seen
        to_return = new_entries[:batch_size]
        has_more = len(new_entries) > batch_size
        next_phase = "backfill" if has_more else "incremental"

        for e in to_return:
            seen_ids.add(e.entry_external_id)

        logger.info(
            "OliveYoung %s: collected %d articles (phase→%s)",
            phase,
            len(to_return),
            next_phase,
        )
        return to_return, {"phase": next_phase, "seen_ids": list(seen_ids)}

    def _fetch_feed(self) -> list[dict] | None:
        """Fetch and parse the RSS feed. Returns feedparser entries or None on error."""
        headers = {"User-Agent": self.user_agent}
        try:
            response = self.session.get(
                OLIVEYOUNG_RSS, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
            raw_xml = response.text
        except Exception as err:
            logger.warning("OliveYoung: RSS fetch failed: %s", err)
            return None

        parsed = feedparser.parse(raw_xml)
        if parsed.bozo and not parsed.entries:
            logger.warning("OliveYoung: RSS parse error: %s", parsed.bozo_exception)
            return None

        logger.info("OliveYoung: fetched %d feed entries", len(parsed.entries))
        return parsed.entries  # type: ignore[return-value]

    def _build_entry(
        self,
        source: SourceConfig,
        fe: dict,
        entry_url: str,
        published_at: str | None,
    ) -> RawEntry | None:
        title = fe.get("title") or None

        # Body: prefer content:encoded, fall back to summary
        content_raw: str | None = None
        for c in fe.get("content", []):
            if c.get("type") in ("text/html", "application/xhtml+xml", ""):
                content_raw = c.get("value")
                break
        if not content_raw:
            content_raw = fe.get("summary") or None

        html_body = content_raw or ""
        body_text = html_to_text(html_body) if html_body else ""

        author = fe.get("author") or None

        # Tags from feedparser
        tags = [t.get("term", "") for t in fe.get("tags", []) if t.get("term")]

        # Thumbnail: try media_thumbnail, then enclosure
        thumbnail_url: str | None = None
        for media in fe.get("media_thumbnail", []):
            thumbnail_url = media.get("url")
            break
        if not thumbnail_url:
            for enc in fe.get("enclosures", []):
                if enc.get("type", "").startswith("image/"):
                    thumbnail_url = enc.get("href")
                    break

        response_hash = sha256_text(html_body)
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
            "OliveYoung entry %s title=%s date=%s body_len=%d",
            entry_url.split("/")[-1][:30],
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
            entry_external_id=entry_url,
            entry_url=entry_url,
            title_raw=title,
            author_raw=author,
            published_at_raw=published_at,
            summary_raw=None,
            content_raw=None,
            html_body_raw=html_body if html_body else None,
            html_text_raw=body_text if len(body_text) > 100 else None,
            thumbnail_url=thumbnail_url,
            categories_raw=tags,
            fetched_at=datetime.now(timezone.utc),
            response_hash=response_hash,
            parser_version="backfill-oliveyoung-v1",
            entry_hash=entry_hash,
        )

    @staticmethod
    def _extract_date(fe: dict) -> str | None:
        """Extract ISO date from feedparser entry."""
        raw = fe.get("published") or fe.get("updated") or None
        if not raw:
            return None
        return normalize_date(raw)
