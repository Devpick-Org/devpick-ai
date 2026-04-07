"""Collect StackOverflow and Velog entries and push to Backend ingest API."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

from app.collectors.stackoverflow import StackOverflowCollector
from app.collectors.velog import VelogCollector
from app.services.push_service import PushService
from app.stores.sent_id_store import SentIdStore


def collect_and_push_direct(
    push_service: PushService,
    sent_id_store: SentIdStore,
    source_name: str,
    contents: list,
) -> None:
    """Push pre-normalized NormalizedContent items (SO, Velog) to backend.

    중복 방지: canonical_url을 entry_id로 사용해 SentIdStore로 dedup.
    """
    sent_ids = sent_id_store.load(source_name)
    new_items = [c for c in contents if c.canonical_url not in sent_ids]

    if not new_items:
        print(f"[SKIP] {source_name} all {len(contents)} items already sent")
        return

    try:
        result = push_service.push(new_items)
        pushed_ids = {c.canonical_url for c in new_items if c.canonical_url}
        sent_id_store.add(source_name, pushed_ids)
        print(
            f"[OK] {source_name} collected={len(contents)} new={len(new_items)}"
            f" pushed={result.get('saved', '?')} skipped={result.get('skipped', '?')}"
        )
    except Exception as error:
        logging.exception("Failed source=%s", source_name)
        print(f"[ERROR] {source_name} error={error}")


def main() -> None:
    """Run collect → push pipeline for StackOverflow and Velog."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8080")
    push_service = PushService(backend_url=backend_url, timeout=30)
    sent_id_store = SentIdStore(base_dir="data/raw/sent_ids")

    # Stack Overflow (API 기반, sort=hot, score≥5, view_count≥500)
    so_tags_raw = os.environ.get("STACKOVERFLOW_TAGS", "java,spring-boot,kotlin,python")
    so_tags = [t.strip() for t in so_tags_raw.split(",") if t.strip()]
    so_collector = StackOverflowCollector(
        api_key=os.environ.get("STACKOVERFLOW_API_KEY"),
        min_score=int(os.environ.get("STACKOVERFLOW_MIN_SCORE", "5")),
        min_views=int(os.environ.get("STACKOVERFLOW_MIN_VIEWS", "500")),
        days_back=int(os.environ.get("STACKOVERFLOW_DAYS_BACK", "7")),
    )
    so_contents = so_collector.fetch(tags=so_tags)
    collect_and_push_direct(push_service, sent_id_store, "stackoverflow", so_contents)

    # Velog (GraphQL 기반, ADR-006: SUMMARY_ONLY, 2026-01-01 이후만)
    velog_collector = VelogCollector(
        min_date=os.environ.get("VELOG_MIN_DATE", "2026-01-01"),
    )
    velog_contents = velog_collector.fetch()
    collect_and_push_direct(push_service, sent_id_store, "velog", velog_contents)


if __name__ == "__main__":
    main()
