"""Inspect raw JSONL and preview minimum normalization results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.raw_content import RawEntry
from app.services.normalize_service import NormalizeService


def resolve_jsonl_path(source: str | None) -> Path | None:
    """Resolve entries JSONL path for a specific source."""
    if source is None:
        return None
    return PROJECT_ROOT / "data" / "raw" / "entries" / source / "entries.jsonl"


def print_normalized_preview(raw_entry: RawEntry, normalizer: NormalizeService) -> None:
    """Print compact normalized view for one raw entry."""
    normalized = normalizer.normalize_entry(raw_entry)
    preview_length = len(normalized.preview or "")
    body_length = len((normalized.body_candidate or "").strip())
    html_text_length = len((raw_entry.html_text_raw or "").strip())

    print(f"- title: {normalized.title}")
    print(f"  content_kind: {normalized.content_kind}")
    print(f"  preview_length: {preview_length}")
    print(f"  body_candidate_length: {body_length}")
    print(f"  body_source: {normalized.body_source}")
    print(f"  html_text_length: {html_text_length}")
    print(f"  canonical_url: {normalized.canonical_url}")


def inspect_source(source: str, limit: int) -> None:
    """Inspect normalized preview for one source JSONL."""
    target = resolve_jsonl_path(source)
    if target is None or not target.exists():
        print(f"Source data not found: {target}")
        return

    normalizer = NormalizeService()
    print(f"\n== source: {source} ==")
    with target.open("r", encoding="utf-8") as file_handle:
        lines = file_handle.readlines()

    for line in lines[-limit:]:
        payload = json.loads(line)
        raw_entry = RawEntry.model_validate(payload)
        print_normalized_preview(raw_entry, normalizer)


def inspect_all(limit: int) -> None:
    """Inspect all source JSONL files under data/raw/entries."""
    entries_root = PROJECT_ROOT / "data" / "raw" / "entries"
    if not entries_root.exists():
        print(f"Entries directory not found: {entries_root}")
        return

    sources = sorted(path.name for path in entries_root.iterdir() if path.is_dir())
    if not sources:
        print(f"No source directories found under: {entries_root}")
        return

    for source in sources:
        inspect_source(source, limit)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect raw entries with normalization preview"
    )
    parser.add_argument(
        "--source", type=str, default=None, help="Source name (e.g., NAVER_D2)"
    )
    parser.add_argument(
        "--limit", type=int, default=3, help="Number of rows to inspect"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.source:
        inspect_source(args.source, args.limit)
    else:
        inspect_all(args.limit)
