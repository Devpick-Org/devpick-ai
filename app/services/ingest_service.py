"""Collector execution orchestration service."""

from __future__ import annotations

import logging
from typing import Protocol

from app.schemas.raw_content import RawEntry, RawFeedMeta
from app.schemas.source import SourceConfig
from app.stores.raw_store import RawStore

logger = logging.getLogger(__name__)


class SupportsRawCollect(Protocol):
    """Collector protocol for feed metadata + entries + raw response output."""

    def collect(
        self, source: SourceConfig
    ) -> tuple[RawFeedMeta, list[RawEntry], str]: ...


class IngestService:
    """Coordinates collector run and raw persistence."""

    def __init__(self, collector: SupportsRawCollect, raw_store: RawStore) -> None:
        self.collector = collector
        self.raw_store = raw_store

    def run_source(self, source: SourceConfig) -> dict[str, int | str]:
        """Run raw ingestion for one source with error isolation."""
        meta, entries, raw_xml = self.collector.collect(source)
        self.raw_store.save_feed(meta, raw_xml)
        saved_count = self.raw_store.save_entries(entries)
        return {
            "source": source.name,
            "saved_entries": saved_count,
            "status": "ok",
        }

    def run_sources(
        self, sources: list[SourceConfig], content_level: int = 2
    ) -> list[dict[str, int | str]]:
        """Run ingestion for active sources matching target content level."""
        results: list[dict[str, int | str]] = []

        for source in sources:
            if not source.active or source.content_level != content_level:
                continue

            try:
                result = self.run_source(source)
                results.append(result)
            except Exception as error:
                logger.exception("Failed to ingest source=%s", source.name)
                results.append(
                    {
                        "source": source.name,
                        "saved_entries": 0,
                        "status": "error",
                        "error": str(error),
                    }
                )

        return results
