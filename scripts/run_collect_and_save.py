"""Collect articles, normalize, and save NormalizedContent to local JSONL.

Runs one collection batch per source using the unified backfill collectors
(both historical backfill and incremental modes).  No Backend push — saves
to ``data/raw/normalized/{source_name}.jsonl`` instead.

Usage::

    # Collect up to 3 articles per source (default)
    python scripts/run_collect_and_save.py

    # Collect more per source
    python scripts/run_collect_and_save.py --batch-size 20

    # Restrict to specific sources
    python scripts/run_collect_and_save.py --source NAVER_D2 --source Toss_Tech
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from typing import Callable

from app.collectors.backfill.base import BackfillCollector
from app.collectors.backfill.generic_rss import GenericRSSBackfillCollector
from app.collectors.backfill.rss_with_fetch import RSSWithFetchBackfillCollector
from app.collectors.backfill.kakao import KakaoBackfillCollector
from app.collectors.backfill.medium_direct import MediumDirectBackfillCollector
from app.collectors.backfill.naver_d2 import NaverD2BackfillCollector
from app.collectors.backfill.toss import TossBackfillCollector
from app.configs.sources import get_all_sources
from app.schemas.raw_content import RawEntry
from app.schemas.source import SourceConfig
from app.services.normalize_service import NormalizeService
from app.stores.backfill_cursor import BackfillCursor
from app.stores.sent_id_store import SentIdStore

_NORMALIZED_DIR = Path("data/raw/normalized")
_SINCE_YEAR = 2026

_COLLECTOR_FACTORIES: dict[str, Callable[[], BackfillCollector]] = {
    "Kakao_Tech": KakaoBackfillCollector,
    "NAVER_D2": NaverD2BackfillCollector,
    "Toss_Tech": TossBackfillCollector,
    "OliveYoung_Tech": GenericRSSBackfillCollector,
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
    "Medium_airbnb-engineering": lambda: MediumDirectBackfillCollector(
        publication="airbnb-engineering"
    ),
    "Medium_pinterest-engineering": lambda: MediumDirectBackfillCollector(
        publication="pinterest-engineering"
    ),
    "Medium_gccompany": lambda: MediumDirectBackfillCollector(publication="gccompany"),
    "Medium_flutter": lambda: MediumDirectBackfillCollector(publication="flutter"),
    "Woowahan_Tech": lambda: GenericRSSBackfillCollector(use_cffi=True),
    "Meta_Engineering": GenericRSSBackfillCollector,
    "Cloudflare_Blog": GenericRSSBackfillCollector,
    "Socar_Tech": GenericRSSBackfillCollector,
    "GitHub_Blog": GenericRSSBackfillCollector,
    "AWS_Korea_Tech": GenericRSSBackfillCollector,
    "Spring_Blog": lambda: RSSWithFetchBackfillCollector(
        extra_body_selectors=["div.markdown"]
    ),
    "SKPlanet_Tech": GenericRSSBackfillCollector,
    "Nongshim_Cloud_Tech": GenericRSSBackfillCollector,
    "MS_DevBlogs": GenericRSSBackfillCollector,
    "NVIDIA_Developer": RSSWithFetchBackfillCollector,
    "Flex_Tech": lambda: RSSWithFetchBackfillCollector(use_cffi=True),
    "Grab_Engineering": RSSWithFetchBackfillCollector,
    "Google_Developers": lambda: RSSWithFetchBackfillCollector(
        extra_body_selectors=["div.blog-detail-container"]
    ),
    "KakaoPay_Tech": RSSWithFetchBackfillCollector,
    "Nextjs_Blog": RSSWithFetchBackfillCollector,
}


def _safe_name(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return sanitized.strip("_") or "unknown_source"


def _is_relevant(entry: RawEntry, source: SourceConfig) -> bool:
    url = entry.entry_url or ""
    title = entry.title_raw or ""
    if source.url_include_pattern and not re.search(source.url_include_pattern, url):
        return False
    if any(kw in title for kw in source.title_blocklist):
        return False
    return True


def collect_and_save(
    normalizer: NormalizeService,
    sent_id_store: SentIdStore,
    cursor_store: BackfillCursor,
    source_filter: list[str] | None = None,
    batch_size: int = 3,
) -> None:
    """Run one collection batch per source and save NormalizedContent locally."""
    sources = get_all_sources()
    if source_filter:
        sources = [s for s in sources if s.name in source_filter]

    for source in sources:
        if not source.active:
            continue

        if cursor_store.is_done(source.name):
            print(f"[SKIP] {source.name} already done (backfill not yet started)")
            continue

        factory = _COLLECTOR_FACTORIES.get(source.name)
        if factory is None:
            print(f"[SKIP] {source.name} — no collector registered")
            continue

        cursor = cursor_store.load(source.name)
        try:
            entries, new_cursor = factory().collect_batch(source, cursor, batch_size)
        except Exception as error:
            logging.exception("Backfill failed source=%s", source.name)
            print(f"[ERROR] {source.name} error={error}")
            continue

        if not entries:
            cursor_store.save(source.name, new_cursor)
            phase = new_cursor.get("phase", "backfill")
            print(f"[EMPTY] {source.name} (phase={phase})")
            continue

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

        new_entries = [e for e in new_entries if _is_relevant(e, source)]

        if not new_entries:
            print(f"[SKIP] {source.name} all {len(entries)} already saved or filtered")
            cursor_store.save(source.name, new_cursor)
            continue

        new_items = [normalizer.normalize_entry(entry) for entry in new_entries]

        _NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _NORMALIZED_DIR / f"{_safe_name(source.name)}.jsonl"
        with out_path.open("a", encoding="utf-8") as fh:
            for item in new_items:
                fh.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False))
                fh.write("\n")

        saved_ids = {e.entry_external_id for e in new_entries}
        sent_id_store.add(source.name, saved_ids)
        cursor_store.save(source.name, new_cursor)

        phase = new_cursor.get("phase", "backfill")
        print(
            f"[OK] {source.name} collected={len(entries)} new={len(new_items)}"
            f" saved={out_path} phase={phase}"
        )
        for item in new_items:
            body_len = len(item.body_candidate or "")
            thumb = "[Y]" if item.thumbnail_url else "[N]"
            print(
                f"  title={ascii((item.title or '')[:50])}"
                f" date={item.published_at or '?'}"
                f" body={body_len}chars thumb={thumb}"
            )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="통합 수집 → 정규화 → 로컬 JSONL 저장 (push 없음)"
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="NAME",
        help="수집할 소스 이름 필터. 여러 번 사용 가능.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=3,
        metavar="N",
        help="소스당 수집 개수 (기본: 3)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    normalizer = NormalizeService()
    sent_id_store = SentIdStore(base_dir="data/raw/sent_ids")
    cursor_store = BackfillCursor(base_dir="data/raw/backfill_cursor")

    collect_and_save(
        normalizer,
        sent_id_store,
        cursor_store,
        source_filter=args.sources,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
