"""콘텐츠 저장 후 요약 파이프라인 오케스트레이터."""

from __future__ import annotations

import logging

from app.repositories.summary_repository import SummaryRepository
from app.services.all_levels_summary_service import AllLevelsSummaryService
from app.services.embedding_service import EmbeddingOrchestrator
from app.services.preprocess_service import PreprocessService

logger = logging.getLogger(__name__)


class ContentPipeline:
    """PostgreSQL 저장 후 즉시 전처리 → 4레벨 요약 → DynamoDB 저장 → 임베딩을 실행한다.

    각 단계는 독립 try/except로 보호되므로 한 단계 실패해도 다음 단계를 계속 시도한다.
    PostgreSQL 저장은 이미 완료된 상태이므로 여기서 실패해도 콘텐츠 유실은 없다.
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        bedrock_model: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
    ) -> None:
        self._preprocess = PreprocessService()
        self._summary_svc = AllLevelsSummaryService(
            aws_region=aws_region, model=bedrock_model
        )
        self._summary_repo = SummaryRepository(aws_region=aws_region)
        self._embedding = EmbeddingOrchestrator(aws_region=aws_region)

    def process_content(
        self,
        content_id: str,
        body_html: str | None,
        thumbnail_url: str | None = None,
    ) -> None:
        """단일 콘텐츠에 대해 전처리 → 요약 → DynamoDB 저장 → 임베딩을 실행한다."""
        if not body_html:
            logger.warning("[pipeline] content_id=%s body 없음 — 요약 스킵", content_id)
            return

        # Step 1: 전처리
        try:
            preprocessed = self._preprocess.preprocess(body_html)
        except Exception:
            logger.exception(
                "[pipeline] content_id=%s 전처리 실패 — 요약 스킵", content_id
            )
            return

        # Step 2: 4레벨 요약
        try:
            summary = self._summary_svc.summarize_all(
                content_id=content_id,
                text=preprocessed,
                thumbnail_url=thumbnail_url,
            )
        except Exception:
            logger.exception(
                "[pipeline] content_id=%s 요약 실패 — DynamoDB 저장 스킵", content_id
            )
            return

        # Step 3: DynamoDB 저장 (fire-and-forget)
        try:
            self._summary_repo.save_all_levels(content_id, summary)
        except Exception:
            logger.exception(
                "[pipeline] content_id=%s DynamoDB 저장 실패 (콘텐츠는 저장됨)",
                content_id,
            )

        # Step 4: 임베딩 (fire-and-forget)
        try:
            self._embedding.embed_and_store(
                content_id=content_id,
                preprocessed_text=preprocessed,
                summary=summary,
            )
        except Exception:
            logger.exception(
                "[pipeline] content_id=%s 임베딩 실패 (요약은 저장됨)", content_id
            )

        logger.info("[pipeline] content_id=%s 처리 완료", content_id)
