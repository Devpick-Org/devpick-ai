"""YouTube 영상 수집 1회 실행 (DP-416).

tags 테이블 키워드를 7일 로테이션으로 수집하고 PostgreSQL에 저장한다.
AI 처리(요약/퀴즈/임베딩)는 실행하지 않는다.

Usage:
    DATABASE_URL=postgresql://... YOUTUBE_API_KEY=... python scripts/run_youtube_batch.py
"""

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")


def main() -> None:
    if not _DATABASE_URL:
        logger.error("DATABASE_URL 환경변수 필요")
        sys.exit(1)

    if not _YOUTUBE_API_KEY:
        logger.warning("YOUTUBE_API_KEY 미설정 — YouTube 수집 스킵")
        return

    from app.collectors.backfill.youtube import YouTubeCollector
    from app.repositories.content_repository import ContentRepository
    from app.stores.sent_id_store import SentIdStore

    collector = YouTubeCollector(
        api_key=_YOUTUBE_API_KEY,
        database_url=_DATABASE_URL,
    )
    content_repo = ContentRepository(database_url=_DATABASE_URL)
    sent_id_store = SentIdStore()

    try:
        logger.info("YouTube 수집 시작")
        items = collector.fetch()
        logger.info("수집 완료: %d개", len(items))

        sent_ids = sent_id_store.load("YouTube")
        new_items = [i for i in items if i.canonical_url not in sent_ids]
        # TODO: 테스트용 — 최대 10개만 저장. 운영 시 아래 줄 제거
        new_items = new_items[:10]
        logger.info("신규 항목: %d개 (중복 제외)", len(new_items))

        if not new_items:
            return

        result = content_repo.save_contents(new_items)
        logger.info("저장 완료: saved=%d skipped=%d", result.saved, result.skipped)

        for content_id, item in result.inserted:
            if item.content_tags:
                content_repo.save_content_tags(content_id, item.content_tags)

        sent_id_store.add(
            "YouTube",
            {i.canonical_url for i in new_items if i.canonical_url},
        )

    except Exception:
        logger.exception("YouTube 수집 배치 실패")
        sys.exit(1)
    finally:
        content_repo.close()


if __name__ == "__main__":
    main()
