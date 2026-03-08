"""Read raw entries, normalize them, and persist normalized content to PostgreSQL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.configs.sources import get_crawl_sources, get_default_sources
from app.db.models import Base
from app.db.session import get_connection_summary, get_engine, get_session_factory
from app.schemas.raw_content import RawEntry
from app.schemas.source import SourceConfig
from app.services.normalize_service import NormalizeService
from app.services.persist_service import PersistService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save normalized contents to PostgreSQL"
    )
    parser.add_argument("--source", required=True, help="Source name (e.g., NAVER_D2)")
    parser.add_argument(
        "--limit", type=int, default=5, help="Number of latest rows to persist"
    )
    return parser.parse_args()


def find_source(source_name: str) -> SourceConfig:
    all_sources = [*get_default_sources(), *get_crawl_sources()]
    for source in all_sources:
        if source.name == source_name:
            return source
    raise ValueError(f"Unknown source: {source_name}")


def read_latest_raw_entries(source_name: str, limit: int) -> list[RawEntry]:
    file_path = (
        PROJECT_ROOT / "data" / "raw" / "entries" / source_name / "entries.jsonl"
    )
    if not file_path.exists():
        raise FileNotFoundError(f"Raw entries file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as file_handle:
        lines = file_handle.readlines()

    selected_lines = lines[-limit:] if limit > 0 else lines
    return [RawEntry.model_validate(json.loads(line)) for line in selected_lines]


def main() -> None:
    args = parse_args()
    source = find_source(args.source)
    raw_entries = read_latest_raw_entries(source.name, args.limit)

    normalize_service = NormalizeService()
    normalized_items = [
        normalize_service.normalize_entry(raw_entry) for raw_entry in raw_entries
    ]

    summary = get_connection_summary()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    session_factory = get_session_factory()
    persist_service = PersistService()

    with session_factory() as session:
        result = persist_service.persist_normalized(
            session,
            source=source,
            normalized_items=normalized_items,
        )

    print(
        f"[DB] mode={summary['mode']} host={summary['host']} port={summary['port']} db={summary['database']} user={summary['user']}"
    )
    print(
        "[OK] "
        f"source={result['source']} "
        f"source_upsert={result['source_upsert_action']} "
        f"contents_saved={result['saved']} "
        f"inserted={result['inserted']} "
        f"updated={result['updated']} "
        f"skipped={result['skipped']}"
    )


def _print_quick_guide() -> None:
    print("\nQuick verification flow:")
    print("1) python scripts/check_db_connection.py")
    print("2) python scripts/save_normalized_to_db.py --source NAVER_D2 --limit 5")
    print("3) python scripts/check_saved_contents.py --source NAVER_D2 --limit 5")


if __name__ == "__main__":
    try:
        main()
        _print_quick_guide()
    except Exception as error:
        print(f"[ERROR] save_normalized_to_db failed: {error}")
        _print_quick_guide()
        raise
