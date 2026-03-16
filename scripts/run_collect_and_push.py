"""Collect RSS entries, normalize, and push to Backend ingest API."""

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

from app.collectors.rss import RSSCollector
from app.collectors.rss_crawl import RSSCrawlCollector
from app.configs.sources import get_crawl_sources, get_default_sources
from app.services.normalize_service import NormalizeService
from app.services.push_service import PushService
from app.stores.file_store import FileRawStore
from app.stores.sent_id_store import SentIdStore


def collect_and_push(
    store: FileRawStore,
    normalizer: NormalizeService,
    push_service: PushService,
    sent_id_store: SentIdStore,
    collector,
    sources: list,
    content_level: int,
) -> None:
    """Run collect → normalize → push for each active source."""
    for source in sources:
        if not source.active or source.content_level != content_level:
            continue

        try:
            meta, entries, raw_xml = collector.collect(source)
            store.save_feed(meta, raw_xml)
            store.save_entries(entries)

            normalized = [normalizer.normalize_entry(entry) for entry in entries]

            sent_ids = sent_id_store.load(source.name)
            new_items = [
                item for item in normalized if item.entry_external_id not in sent_ids
            ]

            if not new_items:
                print(f"[SKIP] {source.name} all {len(normalized)} items already sent")
                continue

            result = push_service.push(new_items)
            pushed_ids = {
                item.entry_external_id for item in new_items if item.entry_external_id
            }
            sent_id_store.add(source.name, pushed_ids)
            print(
                f"[OK] {source.name} collected={len(entries)} new={len(new_items)}"
                f" pushed={result.get('saved', '?')} skipped={result.get('skipped', '?')}"
            )
        except Exception as error:
            logging.exception("Failed source=%s", source.name)
            print(f"[ERROR] {source.name} error={error}")


def main() -> None:
    """Run full collect → normalize → push pipeline for all active sources."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8080")
    store = FileRawStore(base_dir="data/raw")
    normalizer = NormalizeService()
    push_service = PushService(backend_url=backend_url, timeout=30)
    sent_id_store = SentIdStore(base_dir="data/raw/sent_ids")

    # Level-2 RSS/Atom sources
    rss_collector = RSSCollector(timeout=10.0, max_retries=2)
    collect_and_push(
        store,
        normalizer,
        push_service,
        sent_id_store,
        rss_collector,
        get_default_sources(),
        content_level=2,
    )

    # Level-1 RSS+crawl sources
    crawl_collector = RSSCrawlCollector(timeout=10.0, max_retries=2)
    collect_and_push(
        store,
        normalizer,
        push_service,
        sent_id_store,
        crawl_collector,
        get_crawl_sources(),
        content_level=1,
    )


if __name__ == "__main__":
    main()
