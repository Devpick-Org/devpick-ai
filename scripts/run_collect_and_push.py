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
from app.collectors.stackoverflow import StackOverflowCollector
from app.collectors.velog import VelogCollector
from app.configs.sources import get_crawl_sources, get_default_sources
from app.services.normalize_service import NormalizeService
from app.services.push_service import PushService
from app.stores.sent_id_store import SentIdStore


def collect_and_push(
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
            _meta, entries, _raw_xml = collector.collect(source)

            sent_ids = sent_id_store.load(source.name)
            new_entries = [e for e in entries if e.entry_external_id not in sent_ids]

            if not new_entries:
                print(f"[SKIP] {source.name} all {len(entries)} items already sent")
                continue

            new_items = [normalizer.normalize_entry(entry) for entry in new_entries]
            result = push_service.push(new_items)
            pushed_ids = {e.entry_external_id for e in new_entries}
            sent_id_store.add(source.name, pushed_ids)
            print(
                f"[OK] {source.name} collected={len(entries)} new={len(new_items)}"
                f" pushed={result.get('saved', '?')} skipped={result.get('skipped', '?')}"
            )
        except Exception as error:
            logging.exception("Failed source=%s", source.name)
            print(f"[ERROR] {source.name} error={error}")


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
    """Run full collect → normalize → push pipeline for all active sources."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8080")
    normalizer = NormalizeService()
    push_service = PushService(backend_url=backend_url, timeout=30)
    sent_id_store = SentIdStore(base_dir="data/raw/sent_ids")

    # Level-2 RSS/Atom sources
    rss_collector = RSSCollector(timeout=10.0, max_retries=2)
    collect_and_push(
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
        normalizer,
        push_service,
        sent_id_store,
        crawl_collector,
        get_crawl_sources(),
        content_level=1,
    )

    # Stack Overflow (API 기반)
    so_tags_raw = os.environ.get("STACKOVERFLOW_TAGS", "java,spring-boot,kotlin,python")
    so_tags = [t.strip() for t in so_tags_raw.split(",") if t.strip()]
    so_collector = StackOverflowCollector(
        api_key=os.environ.get("STACKOVERFLOW_API_KEY"),
    )
    so_contents = so_collector.fetch(tags=so_tags)
    collect_and_push_direct(push_service, sent_id_store, "stackoverflow", so_contents)

    # Velog (GraphQL 기반, ADR-006: SUMMARY_ONLY)
    velog_collector = VelogCollector()
    velog_contents = velog_collector.fetch()
    collect_and_push_direct(push_service, sent_id_store, "velog", velog_contents)


if __name__ == "__main__":
    main()
