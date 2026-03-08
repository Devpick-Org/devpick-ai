"""Run Kakao RSS+crawl collector and persist enriched raw entries."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.collectors.rss_crawl import RSSCrawlCollector
from app.configs.sources import get_crawl_sources
from app.services.ingest_service import IngestService
from app.stores.file_store import FileRawStore


def main() -> None:
    """Execute Kakao level-1 RSS+crawl collection."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    collector = RSSCrawlCollector(timeout=10.0, max_retries=2)
    store = FileRawStore(base_dir="data/raw")
    service = IngestService(collector=collector, raw_store=store)

    results = service.run_sources(get_crawl_sources(), content_level=1)

    for result in results:
        if result["status"] == "ok":
            print(f"[OK] {result['source']} saved_entries={result['saved_entries']}")
        else:
            print(f"[ERROR] {result['source']} error={result.get('error', 'unknown')}")


if __name__ == "__main__":
    main()
