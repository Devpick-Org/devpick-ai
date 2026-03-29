"""Collect RSS entries, normalize, and save NormalizedContent to local JSONL."""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.collectors.rss import RSSCollector
from app.collectors.rss_crawl import RSSCrawlCollector
from app.configs.sources import get_crawl_sources, get_default_sources
from app.services.normalize_service import NormalizeService
from app.stores.sent_id_store import SentIdStore

_NORMALIZED_DIR = Path("data/raw/normalized")


def _safe_name(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return sanitized.strip("_") or "unknown_source"


def collect_and_save(
    normalizer: NormalizeService,
    sent_id_store: SentIdStore,
    collector,
    sources: list,
    content_level: int,
) -> None:
    """Run collect → normalize → save for each active source."""
    for source in sources:
        if not source.active or source.content_level != content_level:
            continue

        try:
            _meta, entries, _raw_xml = collector.collect(source)

            sent_ids = sent_id_store.load(source.name)
            new_entries = [e for e in entries if e.entry_external_id not in sent_ids]

            if not new_entries:
                print(f"[SKIP] {source.name} all {len(entries)} items already saved")
                continue

            new_items = [normalizer.normalize_entry(entry) for entry in new_entries]

            _NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
            out_path = _NORMALIZED_DIR / f"{_safe_name(source.name)}.jsonl"
            with out_path.open("a", encoding="utf-8") as fh:
                for item in new_items:
                    fh.write(
                        json.dumps(item.model_dump(mode="json"), ensure_ascii=False)
                    )
                    fh.write("\n")

            saved_ids = {e.entry_external_id for e in new_entries}
            sent_id_store.add(source.name, saved_ids)
            print(
                f"[OK] {source.name} collected={len(entries)} new={len(new_items)}"
                f" saved={out_path}"
            )
        except Exception as error:
            logging.exception("Failed source=%s", source.name)
            print(f"[ERROR] {source.name} error={error}")


def main() -> None:
    """Run full collect → normalize → local save pipeline for all active sources."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    normalizer = NormalizeService()
    sent_id_store = SentIdStore(base_dir="data/raw/sent_ids")

    # Level-2 RSS/Atom sources
    rss_collector = RSSCollector(timeout=10.0, max_retries=2)
    collect_and_save(
        normalizer,
        sent_id_store,
        rss_collector,
        get_default_sources(),
        content_level=2,
    )

    # Level-1 RSS+crawl sources
    crawl_collector = RSSCrawlCollector(timeout=10.0, max_retries=2)
    collect_and_save(
        normalizer,
        sent_id_store,
        crawl_collector,
        get_crawl_sources(),
        content_level=1,
    )


if __name__ == "__main__":
    main()
