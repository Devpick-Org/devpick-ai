"""File-based store for tracking successfully pushed entry IDs (cross-run dedup)."""

from __future__ import annotations

import re
from pathlib import Path


class SentIdStore:
    """Persists sent entry IDs per source to prevent re-pushing across runs."""

    def __init__(self, base_dir: str = "data/raw/sent_ids") -> None:
        self.base_path = Path(base_dir)

    def _path(self, source_name: str) -> Path:
        safe = (
            re.sub(r"[^a-zA-Z0-9._-]+", "_", source_name.strip()).strip("_")
            or "unknown"
        )
        return self.base_path / f"{safe}.txt"

    def load(self, source_name: str) -> set[str]:
        path = self._path(source_name)
        if not path.exists():
            return set()
        return set(path.read_text(encoding="utf-8").splitlines())

    def add(self, source_name: str, ids: set[str]) -> None:
        existing = self.load(source_name)
        updated = existing | ids
        path = self._path(source_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(sorted(updated)), encoding="utf-8")
