"""저장된 콘텐츠의 AI 퀴즈를 재생성한다.

content_id를 입력받아 PostgreSQL에서 본문을 조회하고,
QuizService로 4레벨 퀴즈를 재생성한 뒤 DynamoDB에 저장한다.

사용 예:
    DATABASE_URL=postgresql://... python scripts/reprocess_quiz.py <content_id>
    DATABASE_URL=postgresql://... python scripts/reprocess_quiz.py <id1> <id2> <id3>
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

from app.repositories.quiz_repository import QuizRepository
from app.services.preprocess_service import PreprocessService
from app.services.quiz_service import QuizService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _fetch_content(engine, content_id: str) -> dict | None:
    """PostgreSQL에서 content_id에 해당하는 본문을 조회한다."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, original_content FROM contents WHERE id = :id"),
            {"id": content_id},
        ).fetchone()
    if not row:
        return None
    return {
        "content_id": str(row[0]),
        "body_html": row[1],
    }


def reprocess(content_id: str, quiz_svc, preprocess_svc, quiz_repo) -> bool:
    """단일 content_id에 대해 퀴즈를 재생성하고 저장한다."""
    database_url = os.environ.get("DATABASE_URL")
    engine = create_engine(database_url)

    row = _fetch_content(engine, content_id)
    engine.dispose()

    if not row:
        logger.error("[%s] PostgreSQL에서 콘텐츠를 찾을 수 없습니다", content_id)
        return False

    if not row["body_html"]:
        logger.error("[%s] 본문(original_content)이 비어 있습니다", content_id)
        return False

    # 전처리
    try:
        preprocessed = preprocess_svc.preprocess(row["body_html"])
    except Exception:
        logger.exception("[%s] 전처리 실패", content_id)
        return False

    # 퀴즈 생성
    try:
        quiz = quiz_svc.generate_all(content_id=content_id, text=preprocessed)
    except Exception:
        logger.exception("[%s] 퀴즈 생성 실패", content_id)
        return False

    # DynamoDB 저장
    try:
        quiz_repo.save(quiz)
        logger.info("[%s] DynamoDB 저장 완료", content_id)
    except Exception:
        logger.exception("[%s] DynamoDB 저장 실패", content_id)

    return True


def main(content_ids: list[str]) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL이 설정되지 않았습니다 — 실행 중단")
        sys.exit(1)

    aws_region = os.environ.get("AWS_REGION", "ap-northeast-2")
    bedrock_region = os.environ.get("BEDROCK_REGION", "us-east-1")
    bedrock_model = os.environ.get(
        "BEDROCK_MODEL_HAIKU", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    preprocess_svc = PreprocessService()
    quiz_svc = QuizService(aws_region=bedrock_region, model=bedrock_model)
    quiz_repo = QuizRepository(aws_region=aws_region)

    success = 0
    fail = 0
    for content_id in content_ids:
        ok = reprocess(content_id, quiz_svc, preprocess_svc, quiz_repo)
        if ok:
            success += 1
        else:
            fail += 1

    logger.info("완료 — 성공=%d 실패=%d", success, fail)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="저장된 콘텐츠 AI 퀴즈 재생성")
    parser.add_argument("content_ids", nargs="+", metavar="CONTENT_ID")
    args = parser.parse_args()
    main(args.content_ids)
