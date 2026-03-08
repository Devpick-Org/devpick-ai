"""RSS/Atom collector implementation for raw ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.collectors.base import BaseCollector
from app.schemas.raw_content import RawEntry, RawFeedMeta
from app.schemas.source import SourceConfig
from app.utils.xml_helpers import (
    compute_entry_hash,
    detect_parser_type,
    normalize_date,
    safe_get_text,
    sha256_text,
)

logger = logging.getLogger(__name__)


class RSSCollector(BaseCollector):
    """Collects raw entries from RSS/Atom feeds with minimal parsing."""

    def __init__(
        self,
        timeout: float = 10.0,
        max_retries: int = 2,
        user_agent: str = "DevPickAI-RSSCollector/1.0",
        parser_version: str = "rss-raw-v1",
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent
        self.parser_version = parser_version
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

    def collect(self, source: SourceConfig) -> tuple[RawFeedMeta, list[RawEntry], str]:
        """Fetch and parse a feed into raw metadata and entries."""
        headers = {"User-Agent": self.user_agent}
        response = self.session.get(
            source.feed_url, headers=headers, timeout=self.timeout
        )
        response.raise_for_status()

        fetched_at = datetime.now(timezone.utc)
        raw_xml = response.text
        if not raw_xml or not raw_xml.strip():
            raise ValueError(
                f"Empty feed response: source={source.name}, url={source.feed_url}"
            )

        response_hash = sha256_text(raw_xml)
        parsed = feedparser.parse(raw_xml)
        parser_type = detect_parser_type(parsed, parser_type=source.parser_type)

        if parsed.bozo:
            bozo_error = getattr(parsed, "bozo_exception", None)
            logger.warning(
                "Feed parse warning source=%s parser_type=%s error=%s",
                source.name,
                parser_type,
                bozo_error,
            )

        meta = self._build_meta(
            source=source,
            parsed=parsed,
            parser_type=parser_type,
            status_code=response.status_code,
            fetched_at=fetched_at,
            response_hash=response_hash,
            response=response,
        )
        entries = self._parse_entries(
            source=source,
            parsed=parsed,
            parser_type=parser_type,
            fetched_at=fetched_at,
            response_hash=response_hash,
        )

        if not entries:
            logger.warning(
                "No entries parsed source=%s parser_type=%s status=%s",
                source.name,
                parser_type,
                response.status_code,
            )
            if parsed.bozo:
                bozo_error = getattr(parsed, "bozo_exception", None)
                raise ValueError(
                    f"Unable to parse feed entries for source={source.name}, parser={parser_type}, error={bozo_error}"
                )

        return meta, entries, raw_xml

    def _build_meta(
        self,
        source: SourceConfig,
        parsed: feedparser.FeedParserDict,
        parser_type: str,
        status_code: int,
        fetched_at: datetime,
        response_hash: str,
        response: requests.Response,
    ) -> RawFeedMeta:
        return RawFeedMeta(
            source_name=source.name,
            feed_url=source.feed_url,
            site_url=source.site_url,
            parser_type=parser_type,
            http_status=status_code,
            fetched_at=fetched_at,
            response_hash=response_hash,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            title=safe_get_text(parsed.feed.get("title")),
            link=safe_get_text(parsed.feed.get("link"), source.site_url),
            description=safe_get_text(parsed.feed.get("subtitle"))
            or safe_get_text(parsed.feed.get("description")),
        )

    def _parse_entries(
        self,
        source: SourceConfig,
        parsed: feedparser.FeedParserDict,
        parser_type: str,
        fetched_at: datetime,
        response_hash: str,
    ) -> list[RawEntry]:
        entries: list[RawEntry] = []
        for entry in parsed.entries:
            content_candidates = entry.get("content") or []
            content_raw: str | None = None
            if content_candidates and isinstance(content_candidates, list):
                first_content = content_candidates[0]
                if isinstance(first_content, dict):
                    content_raw = safe_get_text(first_content.get("value"))

            summary_raw = safe_get_text(entry.get("summary")) or safe_get_text(
                entry.get("description")
            )
            title_raw = safe_get_text(entry.get("title"))
            entry_url = safe_get_text(entry.get("link"))
            author_raw = (
                safe_get_text(entry.get("author"))
                or safe_get_text(entry.get("dc_creator"))
                or safe_get_text(entry.get("creator"))
            )
            published_raw = normalize_date(
                safe_get_text(entry.get("published"))
                or safe_get_text(entry.get("updated"))
            )

            tags = entry.get("tags") or []
            categories_raw = [
                safe_get_text(tag.get("term"))
                for tag in tags
                if isinstance(tag, dict) and safe_get_text(tag.get("term"))
            ]

            fallback_material = "||".join(
                [
                    source.name,
                    entry_url or "",
                    title_raw or "",
                    published_raw or "",
                    summary_raw or "",
                    content_raw or "",
                ]
            )
            entry_external_id = (
                safe_get_text(entry.get("id"))
                or safe_get_text(entry.get("guid"))
                or entry_url
                or sha256_text(fallback_material)
            )

            entry_hash = compute_entry_hash(
                source_name=source.name,
                entry_external_id=entry_external_id,
                entry_url=entry_url,
                title_raw=title_raw,
                published_at_raw=published_raw,
                summary_raw=summary_raw,
                content_raw=content_raw,
            )

            entries.append(
                RawEntry(
                    source_name=source.name,
                    feed_url=source.feed_url,
                    site_url=source.site_url,
                    parser_type=parser_type,
                    content_level_hint=source.content_level,
                    entry_external_id=entry_external_id,
                    entry_url=entry_url,
                    title_raw=title_raw,
                    author_raw=author_raw,
                    published_at_raw=published_raw,
                    summary_raw=summary_raw,
                    content_raw=content_raw,
                    categories_raw=categories_raw,
                    # feedparser does not provide stable per-entry raw XML fragment access.
                    # Keep this as None and retain full response XML via feed-level storage.
                    raw_xml_fragment=None,
                    fetched_at=fetched_at,
                    response_hash=response_hash,
                    parser_version=self.parser_version,
                    entry_hash=entry_hash,
                )
            )

        return entries
