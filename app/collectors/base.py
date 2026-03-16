"""Common collector interface used by all ingestion types."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.raw_content import RawEntry, RawFeedMeta
from app.schemas.source import SourceConfig


class BaseCollector(ABC):
    """Abstract collector interface for any upstream source."""

    @abstractmethod
    def collect(self, source: SourceConfig) -> tuple[RawFeedMeta, list[RawEntry], str]:
        """Collect raw feed metadata, entries, and raw XML from a source."""
