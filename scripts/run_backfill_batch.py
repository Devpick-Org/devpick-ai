"""Run one collection batch (backfill + incremental) per source and push to Backend.

Designed to be called from the scheduler every 6 hours.  Each invocation picks
up where the previous one left off via per-source cursor files.

Sources transition from ``phase: "backfill"`` (historical scan) to
``phase: "incremental"`` (ongoing new-article check) automatically once the
initial historical range is exhausted.  In incremental phase sources are never
marked done and are always included in each run.

Can also be run standalone::

    BACKEND_URL=http://localhost:8080 python scripts/run_backfill_batch.py
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

from typing import Callable

from app.collectors.backfill.base import BackfillCollector
from app.collectors.backfill.kakao import KakaoBackfillCollector
from app.collectors.backfill.medium_direct import MediumDirectBackfillCollector
from app.collectors.backfill.naver_d2 import NaverD2BackfillCollector
from app.collectors.backfill.oliveyoung import OliveYoungBackfillCollector
from app.collectors.backfill.toss import TossBackfillCollector
from app.configs.sources import get_all_sources
from app.schemas.raw_content import RawEntry
from app.schemas.source import SourceConfig
from app.services.normalize_service import NormalizeService
from app.services.push_service import PushService
from app.stores.backfill_cursor import BackfillCursor
from app.stores.sent_id_store import SentIdStore

logger = logging.getLogger(__name__)

_SINCE_YEAR = 2026

# Source name → factory callable
_COLLECTOR_FACTORIES: dict[str, Callable[[], BackfillCollector]] = {
    "Kakao_Tech": KakaoBackfillCollector,
    "NAVER_D2": NaverD2BackfillCollector,
    "Toss_Tech": TossBackfillCollector,
    "OliveYoung_Tech": OliveYoungBackfillCollector,
    "Medium_daangn": lambda: MediumDirectBackfillCollector(publication="daangn"),
    "Medium_musinsa-tech": lambda: MediumDirectBackfillCollector(
        publication="musinsa-tech"
    ),
    "Medium_myrealtrip-product": lambda: MediumDirectBackfillCollector(
        publication="myrealtrip-product"
    ),
    "Medium_netflix-techblog": lambda: MediumDirectBackfillCollector(
        publication="netflix-techblog"
    ),
}

BATCH_SIZE = 50


def _is_relevant(entry: RawEntry, source: SourceConfig) -> bool:
    """Filter entries by source-level url_include_pattern and title_blocklist."""
    url = entry.entry_url or ""
    title = entry.title_raw or ""
    if source.url_include_pattern and not re.search(source.url_include_pattern, url):
        return False
    if any(kw in title for kw in source.title_blocklist):
        return False
    return True


def _run_source(
    source: SourceConfig,
    normalizer: NormalizeService,
    push_service: PushService,
    sent_id_store: SentIdStore,
    cursor_store: BackfillCursor,
    batch_size: int = BATCH_SIZE,
) -> None:
    """Run one collection batch for a single source."""
    if cursor_store.is_done(source.name):
        logger.info("[SKIP] %s already done (backfill not yet started)", source.name)
        return

    factory = _COLLECTOR_FACTORIES.get(source.name)
    if factory is None:
        logger.warning("[SKIP] %s — no collector registered", source.name)
        return

    collector = factory()
    cursor = cursor_store.load(source.name)

    try:
        entries, new_cursor = collector.collect_batch(source, cursor, batch_size)
    except Exception:
        logger.exception("[ERROR] %s collect_batch failed", source.name)
        return

    if not entries:
        cursor_store.save(source.name, new_cursor)
        phase = new_cursor.get("phase", "backfill")
        logger.info("[EMPTY] %s — 0 entries this batch (phase=%s)", source.name, phase)
        return

    # Dedup via SentIdStore
    sent_ids = sent_id_store.load(source.name)
    new_entries = [e for e in entries if e.entry_external_id not in sent_ids]

    # Year filter
    new_entries = [
        e
        for e in new_entries
        if e.published_at_raw
        and len(e.published_at_raw) >= 4
        and e.published_at_raw[:4].isdigit()
        and int(e.published_at_raw[:4]) >= _SINCE_YEAR
    ]

    # Content relevance filter
    new_entries = [e for e in new_entries if _is_relevant(e, source)]

    if not new_entries:
        logger.info(
            "[SKIP] %s all %d entries already sent or filtered",
            source.name,
            len(entries),
        )
        cursor_store.save(source.name, new_cursor)
        return

    # Normalize
    new_items = [normalizer.normalize_entry(entry) for entry in new_entries]

    # Push to Backend
    try:
        result = push_service.push(new_items)
    except Exception:
        logger.exception("[ERROR] %s push failed", source.name)
        return

    # Record pushed IDs + save cursor
    pushed_ids = {e.entry_external_id for e in new_entries}
    sent_id_store.add(source.name, pushed_ids)
    cursor_store.save(source.name, new_cursor)

    phase = new_cursor.get("phase", "backfill")
    logger.info(
        "[OK] %s collected=%d new=%d pushed=%s skipped=%s phase=%s",
        source.name,
        len(entries),
        len(new_items),
        result.get("saved", "?"),
        result.get("skipped", "?"),
        phase,
    )


def main(batch_size: int = BATCH_SIZE) -> None:
    """Run one collection batch for all active sources."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8080")
    normalizer = NormalizeService()
    push_service = PushService(backend_url=backend_url, timeout=30)
    sent_id_store = SentIdStore(base_dir="data/raw/sent_ids")
    cursor_store = BackfillCursor(base_dir="data/raw/backfill_cursor")

    sources = get_all_sources()

    for source in sources:
        if not source.active:
            continue
        _run_source(
            source, normalizer, push_service, sent_id_store, cursor_store, batch_size
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()
    main(batch_size=args.batch_size)
