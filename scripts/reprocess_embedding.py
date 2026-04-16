"""저장된 콘텐츠의 RAG 임베딩을 재시도한다.

content_id를 입력받아 DynamoDB ai_summaries에서 기존 요약을 조회한다.
요약이 있으면 바로 임베딩을 진행하고, 없으면 요약부터 생성한 뒤 임베딩한다.

사용 예:
    DATABASE_URL=postgresql://... python scripts/reprocess_embedding.py <content_id>
    DATABASE_URL=postgresql://... python scripts/reprocess_embedding.py <id1> <id2> <id3>
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

from app.repositories.summary_repository import SummaryRepository
from app.schemas.summary import (
    AllLevelsSummaryResponse,
    CommonSummary,
    LevelSummary,
)
from app.services.all_levels_summary_service import AllLevelsSummaryService
from app.services.embedding_service import EmbeddingOrchestrator
from app.services.preprocess_service import PreprocessService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _fetch_content(engine, content_id: str) -> dict | None:
    """PostgreSQL에서 content_id에 해당하는 본문·썸네일을 조회한다."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, original_content, thumbnail_url FROM contents WHERE id = :id"
            ),
            {"id": content_id},
        ).fetchone()
    if not row:
        return None
    return {
        "content_id": str(row[0]),
        "body_html": row[1],
        "thumbnail_url": row[2],
    }


def _build_summary_response(
    content_id: str, items: list[dict]
) -> AllLevelsSummaryResponse | None:
    """DynamoDB ai_summaries 아이템 목록에서 AllLevelsSummaryResponse를 재구성한다."""
    if not items:
        return None

    by_level: dict[str, dict] = {item["level"]: item for item in items}
    first = next(iter(by_level.values()))

    common = CommonSummary(
        one_line_summary=first.get("one_line_summary", ""),
        keywords=list(first.get("keywords", [])),
        category=first.get("category", ""),
        tags=list(first.get("tags", [])),
        difficulty=first.get("difficulty", "medium"),
    )

    def _level(item: dict) -> LevelSummary:
        return LevelSummary(
            core_summary=item.get("core_summary", ""),
            key_points=list(item.get("key_points", [])),
            additional_questions=list(item.get("additional_questions", [])),
            next_recommendation=item.get("next_recommendation", ""),
            confidence=float(item.get("confidence", 0.5)),
        )

    fallback = first
    return AllLevelsSummaryResponse(
        content_id=content_id,
        common=common,
        beginner=_level(by_level.get("beginner", fallback)),
        junior=_level(by_level.get("junior", fallback)),
        mid=_level(by_level.get("mid", fallback)),
        senior=_level(by_level.get("senior", fallback)),
        generated_at=first.get("generated_at", ""),
        thumbnail_url=first.get("thumbnail_url"),
    )


def reprocess(
    content_id: str,
    preprocess_svc: PreprocessService,
    summary_svc: AllLevelsSummaryService,
    summary_repo: SummaryRepository,
    embedding_orchestrator: EmbeddingOrchestrator,
    engine,
) -> bool:
    """단일 content_id에 대해 임베딩을 재생성하고 저장한다.

    1. PostgreSQL에서 본문 조회
    2. DynamoDB 요약 존재 여부 확인
       - 있으면 → 바로 임베딩
       - 없으면 → 요약 생성 후 저장 → 임베딩
    """
    row = _fetch_content(engine, content_id)
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

    # 기존 요약 조회
    try:
        summary_items = summary_repo.find_all_levels(content_id)
        summary = _build_summary_response(content_id, summary_items)
    except Exception:
        logger.exception("[%s] DynamoDB 요약 조회 실패", content_id)
        return False

    # 요약이 없으면 생성
    if summary is None:
        logger.info("[%s] 요약 없음 — 요약 생성 시작", content_id)
        try:
            summary = summary_svc.summarize_all(
                content_id=content_id,
                text=preprocessed,
                thumbnail_url=row["thumbnail_url"],
            )
        except Exception:
            logger.exception("[%s] 요약 생성 실패", content_id)
            return False

        try:
            summary_repo.save_all_levels(content_id, summary)
            logger.info("[%s] 요약 DynamoDB 저장 완료", content_id)
        except Exception:
            logger.exception(
                "[%s] 요약 DynamoDB 저장 실패 — 임베딩은 계속 진행", content_id
            )
    else:
        logger.info("[%s] 기존 요약 사용", content_id)

    # 임베딩 생성 + 저장
    try:
        embedding_orchestrator.embed_and_store(
            content_id=content_id,
            preprocessed_text=preprocessed,
            summary=summary,
        )
        logger.info("[%s] 임베딩 저장 완료", content_id)
    except Exception:
        logger.exception("[%s] 임베딩 저장 실패", content_id)
        return False

    return True


def main(content_ids: list[str]) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL이 설정되지 않았습니다 — 실행 중단")
        sys.exit(1)

    aws_region = os.environ.get("AWS_REGION", "ap-northeast-2")
    bedrock_region = os.environ.get("BEDROCK_REGION", "us-east-1")
    bedrock_model_summary = os.environ.get(
        "BEDROCK_MODEL_SUMMARY", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    preprocess_svc = PreprocessService()
    summary_svc = AllLevelsSummaryService(
        aws_region=bedrock_region, model=bedrock_model_summary
    )
    summary_repo = SummaryRepository(aws_region=aws_region)
    embedding_orchestrator = EmbeddingOrchestrator(aws_region=aws_region)
    engine = create_engine(database_url)

    success = 0
    fail = 0
    for content_id in content_ids:
        ok = reprocess(
            content_id,
            preprocess_svc,
            summary_svc,
            summary_repo,
            embedding_orchestrator,
            engine,
        )
        if ok:
            success += 1
        else:
            fail += 1

    engine.dispose()
    logger.info("완료 — 성공=%d 실패=%d", success, fail)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="저장된 콘텐츠 RAG 임베딩 재시도")
    parser.add_argument("content_ids", nargs="+", metavar="CONTENT_ID")
    args = parser.parse_args()
    main(args.content_ids)
