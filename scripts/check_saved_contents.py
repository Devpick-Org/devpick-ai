"""Inspect saved normalized content rows from PostgreSQL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.models import Content, ContentSource
from app.db.session import get_connection_summary, get_session_factory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check saved contents from PostgreSQL")
    parser.add_argument(
        "--source",
        required=False,
        default=None,
        help="Source name filter (e.g., NAVER_D2)",
    )
    parser.add_argument("--limit", type=int, default=5, help="Rows to display")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = get_connection_summary()
    print(
        f"[DB] mode={summary['mode']} host={summary['host']} port={summary['port']} "
        f"db={summary['database']} user={summary['user']}"
    )

    session_factory = get_session_factory()

    with session_factory() as session:
        source_stmt = select(ContentSource)
        if args.source:
            source_stmt = source_stmt.where(ContentSource.name == args.source)
        source_rows = session.execute(source_stmt).scalars().all()

        if not source_rows:
            print("[INFO] No matching sources found.")
            return

        source_ids = [row.id for row in source_rows]
        source_name_by_id = {row.id: row.name for row in source_rows}

        content_stmt = (
            select(Content)
            .where(Content.source_id.in_(source_ids))
            .order_by(Content.updated_at.desc())
            .limit(args.limit)
        )
        content_rows = session.execute(content_stmt).scalars().all()

        if not content_rows:
            print("[INFO] No saved contents found.")
            return

        print(f"[OK] found={len(content_rows)}")
        for row in content_rows:
            metadata = row.metadata_json or {}
            preview_len = len((row.preview or "").strip())
            print("-")
            print(f"  source_name: {source_name_by_id.get(row.source_id)}")
            print(f"  title: {row.title}")
            print(f"  canonical_url: {row.canonical_url}")
            print(f"  published_at: {row.published_at}")
            print(f"  preview_length: {preview_len}")
            print(f"  content_kind: {metadata.get('content_kind')}")
            print(f"  body_source: {metadata.get('body_source')}")


if __name__ == "__main__":
    main()
