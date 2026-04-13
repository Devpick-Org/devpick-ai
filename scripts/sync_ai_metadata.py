"""DynamoDB ai_summaries → PostgreSQL contents tags/category 동기화.

이미 요약이 생성된 콘텐츠 중 PostgreSQL에 tags/category가 없는 항목을
DynamoDB에서 읽어 PostgreSQL에 써준다. LLM 재호출 없음.

사용 예:
    # category IS NULL인 전체 콘텐츠 동기화
    DATABASE_URL=postgresql://... python scripts/sync_ai_metadata.py

    # 특정 content_id만
    DATABASE_URL=postgresql://... python scripts/sync_ai_metadata.py --content-id <id1> <id2>
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

from sqlalchemy import create_engine, text

from app.repositories.content_repository import ContentRepository
from app.repositories.summary_repository import SummaryRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _fetch_no_category_ids(engine) -> list[str]:
    """PostgreSQL에서 category가 없는 content_id 목록을 조회한다."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id FROM contents WHERE category IS NULL ORDER BY created_at")
        ).fetchall()
    return [str(row[0]) for row in rows]


def sync_one(
    content_id: str, summary_repo: SummaryRepository, content_repo: ContentRepository
) -> bool:
    """DynamoDB에서 tags/category를 읽어 PostgreSQL에 업데이트한다."""
    items = summary_repo.find_all_levels(content_id)
    if not items:
        logger.warning("[%s] DynamoDB에 요약 없음 — 스킵", content_id)
        return False

    item = items[0]
    tags = item.get("tags")
    category = item.get("category")

    if not category:
        logger.warning("[%s] DynamoDB 아이템에 category 없음 — 스킵", content_id)
        return False

    # tags가 DynamoDB Set 타입으로 저장된 경우 list로 변환
    if hasattr(tags, "__iter__") and not isinstance(tags, (str, list)):
        tags = list(tags)
    if tags is None:
        tags = []

    try:
        content_repo.save_ai_metadata(
            content_id=content_id,
            tags=tags,
            category=str(category),
        )
        logger.info(
            "[%s] 동기화 완료 — category=%s tags=%s", content_id, category, tags
        )
        return True
    except Exception:
        logger.exception("[%s] PostgreSQL 업데이트 실패", content_id)
        return False


def main(content_ids: list[str] | None = None) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL이 설정되지 않았습니다 — 실행 중단")
        sys.exit(1)

    aws_region = os.environ.get("AWS_REGION", "ap-northeast-2")

    engine = create_engine(database_url)
    summary_repo = SummaryRepository(aws_region=aws_region)
    content_repo = ContentRepository(database_url=database_url)

    if content_ids:
        target_ids = content_ids
        logger.info("지정된 content_id %d개 처리", len(target_ids))
    else:
        target_ids = _fetch_no_category_ids(engine)
        logger.info("category 없는 콘텐츠 %d개 발견", len(target_ids))

    engine.dispose()

    success = 0
    fail = 0
    skip = 0
    for content_id in target_ids:
        ok = sync_one(content_id, summary_repo, content_repo)
        if ok:
            success += 1
        else:
            skip += 1

    content_repo.close()
    logger.info("완료 — 동기화=%d 스킵(DynamoDB 없음)=%d 실패=%d", success, skip, fail)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="DynamoDB → PostgreSQL tags/category 동기화"
    )
    parser.add_argument(
        "--content-id",
        nargs="+",
        metavar="CONTENT_ID",
        help="특정 content_id만 처리 (생략 시 category IS NULL 전체 처리)",
    )
    args = parser.parse_args()
    main(content_ids=args.content_id)
