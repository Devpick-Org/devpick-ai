"""Base class for backfill collectors with cursor-based batch crawling."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.raw_content import RawEntry
from app.schemas.source import SourceConfig


class BackfillCollector(ABC):
    """Abstract base for cursor-driven article collectors.

    Two phases:

    * **backfill** — scan historical articles from newest to oldest until
      the configured ``since`` date is reached.  When exhausted the cursor
      transitions to ``phase: "incremental"`` instead of ``done: True``.

    * **incremental** — called on every scheduled run (e.g. every 6 hours)
      to pick up newly published articles.  The cursor is *never* marked
      ``done: True`` in this phase so the scheduler keeps running it.

    Cursor convention shared across all subclasses::

        {"phase": "backfill" | "incremental", ...source-specific fields...}

    The ``done`` key is kept for backward compatibility but should only be
    ``True`` temporarily during a phase transition (subclasses handle it).
    """

    @abstractmethod
    def collect_batch(
        self, source: SourceConfig, cursor: dict, batch_size: int = 20
    ) -> tuple[list[RawEntry], dict]:
        """Collect up to *batch_size* articles starting from *cursor*.

        Returns:
            ``(entries, new_cursor)``.  In incremental phase the cursor is
            never marked ``done: True``; in backfill phase it transitions to
            incremental once the historical range is exhausted.
        """

    @staticmethod
    def _resolve_phase(cursor: dict) -> str:
        """Return the current phase, handling legacy cursors without ``phase``.

        Legacy cursors (written before the phase field existed):
        - ``{"done": True, ...}``  → treat as "incremental" (backfill complete)
        - ``{...}`` without phase  → treat as "backfill" (in progress)
        """
        if "phase" in cursor:
            return cursor["phase"]
        if cursor.get("done"):
            return "incremental"
        return "backfill"
