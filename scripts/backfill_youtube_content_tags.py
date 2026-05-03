"""YouTube 기존 콘텐츠 content_tags 백필 (DP-200/201).

content_tags가 없는 YouTube 영상의 title+preview로 태그 매칭 후 INSERT.

Usage:
    DATABASE_URL=postgresql://... python scripts/backfill_youtube_content_tags.py
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


def main() -> None:
    if not _DATABASE_URL:
        logger.error("DATABASE_URL 환경변수 필요")
        sys.exit(1)

    from sqlalchemy import create_engine, text

    engine = create_engine(_DATABASE_URL, pool_pre_ping=True)

    try:
        with engine.connect() as conn:
            # content_tags 없는 YouTube 영상 조회
            rows = conn.execute(text("""
                SELECT c.id, c.title, c.preview
                FROM contents c
                JOIN content_sources cs ON c.source_id = cs.id
                WHERE cs.name = 'YouTube'
                  AND NOT EXISTS (
                    SELECT 1 FROM content_tags ct WHERE ct.content_id = c.id
                  )
            """)).fetchall()

            if not rows:
                logger.info("content_tags 없는 YouTube 영상 없음 — 스킵")
                return

            logger.info("처리 대상: %d개", len(rows))

            # 전체 태그 목록 로드
            tag_rows = conn.execute(text("SELECT id, name FROM tags")).fetchall()
            all_tags = [(str(r[0]), r[1]) for r in tag_rows]
            logger.info("태그 목록: %d개", len(all_tags))

        inserted_total = 0
        skipped_total = 0

        for content_id, title, preview in rows:
            text_blob = ((title or "") + " " + (preview or "")).lower()
            matched_tag_ids = [
                tag_id for tag_id, tag_name in all_tags
                if tag_name.lower() in text_blob
            ]

            if not matched_tag_ids:
                skipped_total += 1
                logger.debug("태그 매칭 없음: content_id=%s title=%s", content_id, title)
                continue

            with engine.begin() as conn:
                for tag_id in matched_tag_ids:
                    conn.execute(
                        text(
                            "INSERT INTO content_tags (content_id, tag_id, created_at)"
                            " VALUES (:content_id, :tag_id, NOW())"
                            " ON CONFLICT DO NOTHING"
                        ),
                        {"content_id": content_id, "tag_id": tag_id},
                    )
            inserted_total += 1
            logger.debug(
                "content_tags 저장: content_id=%s tags=%d개",
                content_id,
                len(matched_tag_ids),
            )

        logger.info(
            "완료 — 태그 저장: %d개 / 태그 없음(스킵): %d개",
            inserted_total,
            skipped_total,
        )

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
