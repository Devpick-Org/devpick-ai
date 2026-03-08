"""Storage interface for raw collected content."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.raw_content import RawEntry, RawFeedMeta


class RawStore(ABC):
    """Abstract storage backend for raw ingestion data."""

    @abstractmethod
    def save_feed(self, meta: RawFeedMeta, raw_xml: str) -> Path:
        """Persist feed-level metadata and full raw XML payload."""

    @abstractmethod
    def save_entries(self, entries: list[RawEntry]) -> int:
        """Persist raw entries and return saved count."""
