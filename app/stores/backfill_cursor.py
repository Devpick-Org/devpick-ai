"""File-based cursor store for tracking backfill progress per source."""

from __future__ import annotations

import json
import re
from pathlib import Path


class BackfillCursor:
    """Persists backfill progress per source as JSON files.

    Each source gets its own JSON file under *base_dir*.
    The cursor dict is source-specific (e.g. ``{"next_id": 700, "done": false}``
    for Kakao, ``{"next_page": 3, "pending_ids": [...], "done": false}`` for D2).
    """

    def __init__(self, base_dir: str = "data/raw/backfill_cursor") -> None:
        self.base_path = Path(base_dir)

    def _path(self, source_name: str) -> Path:
        safe = (
            re.sub(r"[^a-zA-Z0-9._-]+", "_", source_name.strip()).strip("_")
            or "unknown"
        )
        return self.base_path / f"{safe}.json"

    def load(self, source_name: str) -> dict:
        """Load cursor for *source_name*. Returns empty dict if no cursor exists."""
        path = self._path(source_name)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, source_name: str, cursor: dict) -> None:
        """Persist *cursor* for *source_name*."""
        path = self._path(source_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(cursor, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def is_done(self, source_name: str) -> bool:
        """Return True only if backfill is complete AND not yet in incremental mode.

        Sources in ``phase: "incremental"`` are never considered done — the
        scheduler should keep calling them to pick up newly published articles.
        """
        cursor = self.load(source_name)
        if cursor.get("phase") == "incremental":
            return False
        return cursor.get("done", False)

    def reset(self, source_name: str) -> None:
        """Delete cursor file to restart backfill from the beginning."""
        path = self._path(source_name)
        if path.exists():
            path.unlink()
