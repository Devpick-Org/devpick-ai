"""File-based raw storage implementation (JSONL)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re

from app.schemas.raw_content import RawEntry, RawFeedMeta
from app.stores.raw_store import RawStore


class FileRawStore(RawStore):
    """Stores feed JSON and entry JSONL files under data/raw."""

    def __init__(self, base_dir: str = "data/raw") -> None:
        self.base_path = Path(base_dir)
        self.base_path.mkdir(parents=True, exist_ok=True)
        (self.base_path / "feeds").mkdir(parents=True, exist_ok=True)
        (self.base_path / "entries").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(name: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
        return sanitized.strip("_") or "unknown_source"

    def save_feed(self, meta: RawFeedMeta, raw_xml: str) -> Path:
        source_name = self._safe_name(meta.source_name)
        feed_dir = self.base_path / "feeds" / source_name
        feed_dir.mkdir(parents=True, exist_ok=True)

        fetched_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        short_hash = meta.response_hash[:12]
        file_path = feed_dir / f"{fetched_at}_{short_hash}.json"

        payload = {
            "meta": meta.model_dump(mode="json"),
            "raw_xml": raw_xml,
        }

        with file_path.open("w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, ensure_ascii=False, indent=2)

        return file_path

    def save_entries(self, entries: list[RawEntry]) -> int:
        if not entries:
            return 0

        source_name = self._safe_name(entries[0].source_name)
        entry_dir = self.base_path / "entries" / source_name
        entry_dir.mkdir(parents=True, exist_ok=True)

        target = entry_dir / "entries.jsonl"
        with target.open("a", encoding="utf-8") as file_handle:
            for entry in entries:
                file_handle.write(
                    json.dumps(entry.model_dump(mode="json"), ensure_ascii=False)
                )
                file_handle.write("\n")
        return len(entries)
