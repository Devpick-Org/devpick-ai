"""RSS + HTML crawl collector implementation."""

from __future__ import annotations

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.collectors.rss import RSSCollector
from app.schemas.raw_content import RawEntry, RawFeedMeta
from app.schemas.source import SourceConfig
from app.utils.html_helpers import (
    MIN_MEANINGFUL_TEXT_LENGTH,
    extract_kakao_article_body_result,
)

logger = logging.getLogger(__name__)


class RSSCrawlCollector:
    """Collect feed entries and enrich each entry with crawled HTML body data."""

    def __init__(
        self,
        timeout: float = 10.0,
        max_retries: int = 2,
        user_agent: str = "DevPickAI-RSSCrawlCollector/1.0",
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent
        self.rss_collector = RSSCollector(
            timeout=timeout,
            max_retries=max_retries,
            user_agent=user_agent,
            parser_version="rss-crawl-v1",
        )

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
        """Collect RSS raw entries then enrich them with HTML body candidates."""
        meta, entries, raw_xml = self.rss_collector.collect(source)
        enriched_entries = [self._enrich_entry(source.name, entry) for entry in entries]
        return meta, enriched_entries, raw_xml

    def _enrich_entry(self, source_name: str, entry: RawEntry) -> RawEntry:
        """Fetch article page and attach HTML-based body candidates when available."""
        if not entry.entry_url:
            return entry

        headers = {"User-Agent": self.user_agent}
        try:
            response = self.session.get(
                entry.entry_url, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
        except Exception as error:
            logger.warning(
                "Failed crawl source=%s url=%s error=%s",
                source_name,
                entry.entry_url,
                error,
            )
            return entry

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "html" not in content_type and not response.text.lstrip().startswith("<"):
            logger.warning(
                "Non-HTML response source=%s url=%s content_type=%s",
                source_name,
                entry.entry_url,
                content_type,
            )
            return entry

        result = extract_kakao_article_body_result(response.text)
        if result.body_html is None or result.body_text is None:
            logger.warning(
                "Body extraction failed source=%s url=%s selector_miss=%s selectors_tried=%s best_text_len=%s fallback_used=%s",
                source_name,
                entry.entry_url,
                True,
                result.selectors_tried,
                result.best_text_len,
                result.fallback_used,
            )
            return entry

        if len(result.body_text.strip()) < MIN_MEANINGFUL_TEXT_LENGTH:
            logger.warning(
                "Body extraction too short source=%s url=%s method=%s detail=%s text_len=%s selectors_tried=%s fallback_used=%s",
                source_name,
                entry.entry_url,
                result.method,
                result.detail,
                len(result.body_text.strip()),
                result.selectors_tried,
                result.fallback_used,
            )

        logger.info(
            "Body extraction success source=%s url=%s method=%s selected=%s text_len=%s",
            source_name,
            entry.entry_url,
            result.method,
            result.detail,
            len((result.body_text or "").strip()),
        )

        return entry.model_copy(
            update={
                "html_body_raw": result.body_html,
                "html_text_raw": result.body_text,
            }
        )
