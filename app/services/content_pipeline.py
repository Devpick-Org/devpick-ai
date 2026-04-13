"""콘텐츠 저장 후 요약 + 퀴즈 파이프라인 오케스트레이터."""

from __future__ import annotations

import logging

from app.repositories.content_repository import ContentRepository
from app.repositories.quiz_repository import QuizRepository
from app.repositories.summary_repository import SummaryRepository
from app.services.all_levels_summary_service import AllLevelsSummaryService
from app.services.embedding_service import EmbeddingOrchestrator
from app.services.preprocess_service import PreprocessService
from app.services.quiz_service import QuizService

logger = logging.getLogger(__name__)


class ContentPipeline:
    """PostgreSQL 저장 후 즉시 전처리 → 4레벨 요약 → DynamoDB 저장 → 임베딩 → 퀴즈 생성을 실행한다.

    요약(Steps 2~4)과 퀴즈(Step 5)는 서로 독립적으로 실행된다.
    요약이 실패해도 퀴즈 생성은 계속 시도하며, 각 단계 실패는 콘텐츠 유실 없이 로그만 남긴다.
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        bedrock_region: str = "us-east-1",
        bedrock_model: str = "global.anthropic.claude-sonnet-4-6",
        bedrock_model_summary: str = "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        database_url: str | None = None,
    ) -> None:
        self._preprocess = PreprocessService()
        self._content_repo: ContentRepository | None = (
            ContentRepository(database_url) if database_url else None
        )
        self._summary_svc = AllLevelsSummaryService(
            aws_region=bedrock_region, model=bedrock_model_summary
        )
        self._summary_repo = SummaryRepository(aws_region=aws_region)
        self._embedding = EmbeddingOrchestrator(aws_region=aws_region)
        self._quiz_svc = QuizService(aws_region=bedrock_region, model=bedrock_model)
        self._quiz_repo = QuizRepository(aws_region=aws_region)

    def process_content(
        self,
        content_id: str,
        body_html: str | None,
        thumbnail_url: str | None = None,
    ) -> None:
        """단일 콘텐츠에 대해 전처리 → 요약 → DynamoDB 저장 → 임베딩 → 퀴즈 생성을 실행한다."""
        if not body_html:
            logger.warning("[pipeline] content_id=%s body 없음 — 스킵", content_id)
            return

        # Step 1: 전처리
        try:
            preprocessed = self._preprocess.preprocess(body_html)
        except Exception:
            logger.exception(
                "[pipeline] content_id=%s 전처리 실패 — 요약/퀴즈 스킵", content_id
            )
            return

        # Step 2: 4레벨 요약
        summary = None
        try:
            summary = self._summary_svc.summarize_all(
                content_id=content_id,
                text=preprocessed,
                thumbnail_url=thumbnail_url,
            )
        except Exception:
            logger.exception("[pipeline] content_id=%s 요약 실패", content_id)

        # Step 3: 요약 DynamoDB 저장 (fire-and-forget)
        if summary:
            try:
                self._summary_repo.save_all_levels(content_id, summary)
            except Exception:
                logger.exception(
                    "[pipeline] content_id=%s 요약 DynamoDB 저장 실패", content_id
                )

        # Step 3-1: AI 태그·카테고리 PostgreSQL 저장 (fire-and-forget)
        if summary and self._content_repo:
            try:
                self._content_repo.save_ai_metadata(
                    content_id=content_id,
                    tags=summary.common.tags,
                    category=summary.common.category,
                )
            except Exception:
                logger.exception(
                    "[pipeline] content_id=%s AI metadata PostgreSQL 저장 실패",
                    content_id,
                )

        # Step 4: 임베딩 (fire-and-forget)
        if summary:
            try:
                self._embedding.embed_and_store(
                    content_id=content_id,
                    preprocessed_text=preprocessed,
                    summary=summary,
                )
            except Exception:
                logger.exception("[pipeline] content_id=%s 임베딩 실패", content_id)

        # Step 5: 퀴즈 생성 + DynamoDB 저장 (fire-and-forget, 요약과 독립)
        try:
            quiz = self._quiz_svc.generate_all(content_id=content_id, text=preprocessed)
            self._quiz_repo.save(quiz)
        except Exception:
            logger.exception("[pipeline] content_id=%s 퀴즈 생성 실패", content_id)

        logger.info("[pipeline] content_id=%s 처리 완료", content_id)
