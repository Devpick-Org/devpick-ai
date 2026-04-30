"""Run one collection batch (backfill + incremental) per source and save to PostgreSQL.

Designed to be called from the scheduler every 6 hours.  Each invocation picks
up where the previous one left off via per-source cursor files.

Sources transition from ``phase: "backfill"`` (historical scan) to
``phase: "incremental"`` (ongoing new-article check) automatically once the
initial historical range is exhausted.  In incremental phase sources are never
marked done and are always included in each run.

Can also be run standalone::

    DATABASE_URL=postgresql://... python scripts/run_backfill_batch.py
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
from app.collectors.backfill.generic_rss import GenericRSSBackfillCollector
from app.collectors.backfill.rss_with_fetch import RSSWithFetchBackfillCollector
from app.collectors.backfill.kakao import KakaoBackfillCollector
from app.collectors.backfill.medium_direct import MediumDirectBackfillCollector
from app.collectors.backfill.naver_d2 import NaverD2BackfillCollector
from app.collectors.backfill.stackoverflow import StackOverflowBackfillCollector
from app.collectors.backfill.toss import TossBackfillCollector
from app.collectors.backfill.velog import VelogBackfillCollector
from app.configs.sources import get_all_sources, GLOBAL_TITLE_BLOCKLIST
from app.repositories.content_repository import ContentRepository
from app.schemas.normalized_content import NormalizedContent
from app.schemas.raw_content import RawEntry
from app.schemas.source import SourceConfig
from app.services.content_pipeline import ContentPipeline
from app.services.normalize_service import NormalizeService
from app.stores.backfill_cursor import BackfillCursor
from app.stores.sent_id_store import SentIdStore

logger = logging.getLogger(__name__)

_SINCE_YEAR = 2026

# Source name → factory callable (RawEntry 기반 BackfillCollector)
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

# Source name → factory callable (NormalizedContent 직접 반환)
_DIRECT_COLLECTOR_FACTORIES: dict[str, Callable] = {
    "Stack_Overflow": lambda: StackOverflowBackfillCollector(
        api_key=os.environ.get("STACKOVERFLOW_API_KEY")
    ),
    "Velog": lambda: VelogBackfillCollector(
        min_date=os.environ.get("VELOG_MIN_DATE", "2026-01-01")
    ),
}

BATCH_SIZE = 50


def _is_relevant(entry: RawEntry, source: SourceConfig) -> bool:
    """Filter entries by url_include_pattern and title blocklists (global + per-source)."""
    url = entry.entry_url or ""
    title = entry.title_raw or ""
    if source.url_include_pattern and not re.search(source.url_include_pattern, url):
        return False
    if any(kw in title for kw in GLOBAL_TITLE_BLOCKLIST):
        return False
    if any(kw in title for kw in source.title_blocklist):
        return False
    return True


def _run_source(
    source: SourceConfig,
    normalizer: NormalizeService,
    content_repo: ContentRepository,
    pipeline: ContentPipeline,
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
    new_items = [
        normalizer.normalize_entry(entry, skip_thumbnail=source.skip_thumbnail)
        for entry in new_entries
    ]

    # PostgreSQL 저장
    try:
        result = content_repo.save_contents(new_items)
    except Exception:
        logger.exception("[ERROR] %s PostgreSQL 저장 실패", source.name)
        return

    # 저장 완료된 ID 기록 + 커서 갱신
    pushed_ids = {e.entry_external_id for e in new_entries}
    sent_id_store.add(source.name, pushed_ids)
    cursor_store.save(source.name, new_cursor)

    # 신규 저장된 콘텐츠만 요약 실행 (중복 스킵된 항목 제외)
    for content_id, item in result.inserted:
        try:
            pipeline.process_content(
                content_id=content_id,
                body_html=item.pipeline_body or item.body_candidate,
                thumbnail_url=item.thumbnail_url,
                title=item.title,
            )
        except Exception:
            logger.exception(
                "[WARN] %s 요약 실패 content_id=%s (콘텐츠는 저장됨)",
                source.name,
                content_id,
            )

    phase = new_cursor.get("phase", "backfill")
    logger.info(
        "[OK] %s collected=%d new=%d saved=%d skipped=%d phase=%s",
        source.name,
        len(entries),
        len(new_items),
        result.saved,
        result.skipped,
        phase,
    )


def _run_direct_source(
    source: SourceConfig,
    content_repo: ContentRepository,
    pipeline: ContentPipeline,
    sent_id_store: SentIdStore,
    cursor_store: BackfillCursor,
    batch_size: int = BATCH_SIZE,
) -> None:
    """NormalizedContent를 직접 반환하는 수집기(SO, Velog)용 실행 함수."""
    factory = _DIRECT_COLLECTOR_FACTORIES.get(source.name)
    if factory is None:
        logger.warning("[SKIP] %s — no direct collector registered", source.name)
        return

    collector = factory()
    cursor = cursor_store.load(source.name)

    try:
        items, new_cursor = collector.collect_batch_normalized(cursor, batch_size)
    except Exception:
        logger.exception("[ERROR] %s collect_batch_normalized failed", source.name)
        return

    if not items:
        cursor_store.save(source.name, new_cursor)
        phase = new_cursor.get("phase", "backfill")
        logger.info("[EMPTY] %s — 0 items this batch (phase=%s)", source.name, phase)
        return

    # Dedup via SentIdStore (canonical_url을 외부 ID로 사용)
    sent_ids = sent_id_store.load(source.name)
    new_items: list[NormalizedContent] = [
        item
        for item in items
        if item.canonical_url and item.canonical_url not in sent_ids
    ]

    if not new_items:
        logger.info("[SKIP] %s all %d items already sent", source.name, len(items))
        cursor_store.save(source.name, new_cursor)
        return

    # PostgreSQL 저장
    try:
        result = content_repo.save_contents(new_items)
    except Exception:
        logger.exception("[ERROR] %s PostgreSQL 저장 실패", source.name)
        return

    # 처리 완료 ID 기록 + 커서 갱신
    pushed_ids = {item.canonical_url for item in new_items if item.canonical_url}
    sent_id_store.add(source.name, pushed_ids)
    cursor_store.save(source.name, new_cursor)

    # 신규 저장된 콘텐츠만 요약 실행
    for content_id, item in result.inserted:
        try:
            pipeline.process_content(
                content_id=content_id,
                body_html=item.pipeline_body or item.body_candidate,
                thumbnail_url=item.thumbnail_url,
                title=item.title,
            )
        except Exception:
            logger.exception(
                "[WARN] %s 요약 실패 content_id=%s (콘텐츠는 저장됨)",
                source.name,
                content_id,
            )

    phase = new_cursor.get("phase", "backfill")
    logger.info(
        "[OK] %s collected=%d new=%d saved=%d skipped=%d phase=%s",
        source.name,
        len(items),
        len(new_items),
        result.saved,
        result.skipped,
        phase,
    )


def main(batch_size: int = BATCH_SIZE, only_sources: set[str] | None = None) -> None:
    """Run one collection batch for all active sources."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL이 설정되지 않았습니다 — 실행 중단")
        return

    aws_region = os.environ.get("AWS_REGION", "ap-northeast-2")
    bedrock_region = os.environ.get("BEDROCK_REGION", "us-east-1")
    haiku_model = os.environ.get(
        "BEDROCK_MODEL_HAIKU", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    normalizer = NormalizeService()
    content_repo = ContentRepository(database_url=database_url)
    pipeline = ContentPipeline(
        aws_region=aws_region,
        bedrock_region=bedrock_region,
        haiku_model=haiku_model,
        database_url=database_url,
    )
    sent_id_store = SentIdStore(base_dir="data/raw/sent_ids")
    cursor_store = BackfillCursor(base_dir="data/raw/backfill_cursor")

    sources = get_all_sources()

    for source in sources:
        if not source.active:
            continue
        if only_sources and source.name not in only_sources:
            continue
        if source.name in _DIRECT_COLLECTOR_FACTORIES:
            _run_direct_source(
                source,
                content_repo,
                pipeline,
                sent_id_store,
                cursor_store,
                batch_size,
            )
        else:
            _run_source(
                source,
                normalizer,
                content_repo,
                pipeline,
                sent_id_store,
                cursor_store,
                batch_size,
            )

    content_repo.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="SOURCE_NAME",
        help="특정 소스만 실행 (여러 번 지정 가능). 예: --source Stack_Overflow --source Velog",
    )
    args = parser.parse_args()
    main(
        batch_size=args.batch_size,
        only_sources=set(args.sources) if args.sources else None,
    )
