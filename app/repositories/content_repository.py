"""PostgreSQL contents/content_sources 저장 레이어."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.schemas.normalized_content import NormalizedContent

logger = logging.getLogger(__name__)


@dataclass
class SaveResult:
    saved: int = 0
    skipped: int = 0
    inserted: list[tuple[str, NormalizedContent]] = field(default_factory=list)


class ContentRepository:
    """NormalizedContent를 PostgreSQL contents 테이블에 저장한다.

    content_sources는 source_name으로 조회하고 없으면 자동 생성한다.
    dedup은 canonical_url UNIQUE 인덱스 기반 ON CONFLICT DO NOTHING으로 처리한다.
    """

    def __init__(self, database_url: str, pool_size: int = 5) -> None:
        self._engine: Engine = create_engine(
            database_url,
            pool_size=pool_size,
            pool_pre_ping=True,
        )
        self._source_cache: dict[str, str] = {}

    def _get_or_create_source(self, conn, source_name: str) -> str:
        """content_sources에서 name으로 id를 조회하고 없으면 생성한다."""
        if source_name in self._source_cache:
            return self._source_cache[source_name]

        row = conn.execute(
            text("SELECT id FROM content_sources WHERE name = :name"),
            {"name": source_name},
        ).fetchone()

        if row:
            source_id = str(row[0])
        else:
            source_id = str(uuid4())
            conn.execute(
                text("""
                    INSERT INTO content_sources
                        (id, name, url, collect_method, is_active, created_at)
                    VALUES
                        (:id, :name, '', 'AI_PIPELINE', true, :now)
                    ON CONFLICT (name) DO NOTHING
                """),
                {
                    "id": source_id,
                    "name": source_name,
                    "now": datetime.now(tz=timezone.utc),
                },
            )
            # ON CONFLICT 시 다른 프로세스가 먼저 생성했을 수 있으므로 재조회
            row = conn.execute(
                text("SELECT id FROM content_sources WHERE name = :name"),
                {"name": source_name},
            ).fetchone()
            if row:
                source_id = str(row[0])

        self._source_cache[source_name] = source_id
        return source_id

    def save_contents(self, items: list[NormalizedContent]) -> SaveResult:
        """NormalizedContent 목록을 contents 테이블에 INSERT한다.

        canonical_url 중복 시 ON CONFLICT DO NOTHING으로 스킵한다.
        canonical_url이 없는 항목도 스킵한다.

        Returns:
            SaveResult — saved/skipped 카운트 + 신규 저장된 (content_id, item) 목록.
        """
        if not items:
            return SaveResult()

        result = SaveResult()

        with self._engine.begin() as conn:
            for item in items:
                if not item.canonical_url:
                    logger.warning(
                        "canonical_url 없음 — 저장 스킵: title=%s", item.title
                    )
                    result.skipped += 1
                    continue

                source_id = self._get_or_create_source(conn, item.source_name)
                content_id = str(uuid4())
                now = datetime.now(tz=timezone.utc)

                published_at = None
                if item.published_at:
                    try:
                        published_at = datetime.fromisoformat(item.published_at)
                    except ValueError:
                        logger.warning(
                            "published_at 파싱 실패 (무시): %s", item.published_at
                        )

                row = conn.execute(
                    text("""
                        INSERT INTO contents (
                            id, source_id, title, author, canonical_url,
                            preview, thumbnail_url, thumbnail_width, thumbnail_height,
                            is_original_visible, license_type,
                            original_content, published_at, is_available, is_answered,
                            score, view_count, likes, comments_count,
                            question_content, accepted_answer,
                            top_answers, created_at, updated_at
                        ) VALUES (
                            :id, :source_id, :title, :author, :canonical_url,
                            :preview, :thumbnail_url, :thumbnail_width, :thumbnail_height,
                            :is_original_visible, :license_type,
                            :original_content, :published_at, :is_available, :is_answered,
                            :score, :view_count, :likes, :comments_count,
                            :question_content, :accepted_answer,
                            :top_answers, :created_at, :updated_at
                        )
                        ON CONFLICT DO NOTHING
                        RETURNING id
                    """),
                    {
                        "id": content_id,
                        "source_id": source_id,
                        "title": item.title,
                        "author": item.author,
                        "canonical_url": item.canonical_url,
                        "preview": item.preview,
                        "thumbnail_url": item.thumbnail_url,
                        "thumbnail_width": item.thumbnail_width,
                        "thumbnail_height": item.thumbnail_height,
                        "is_original_visible": item.is_original_visible,
                        "license_type": item.license_type,
                        "original_content": item.body_candidate,
                        "published_at": published_at,
                        "is_available": True,
                        "is_answered": item.is_answered,
                        "score": item.score,
                        "view_count": item.view_count,
                        "likes": item.likes,
                        "comments_count": item.comments_count,
                        "question_content": item.question_content,
                        "accepted_answer": (
                            json.dumps(item.accepted_answer, ensure_ascii=False)
                            if item.accepted_answer is not None
                            else None
                        ),
                        "top_answers": (
                            json.dumps(item.top_answers, ensure_ascii=False)
                            if item.top_answers
                            else None
                        ),
                        "created_at": now,
                        "updated_at": now,
                    },
                ).fetchone()

                if row:
                    result.saved += 1
                    result.inserted.append((str(row[0]), item))
                else:
                    result.skipped += 1

        logger.info(
            "PostgreSQL 저장 완료: saved=%d skipped=%d", result.saved, result.skipped
        )
        return result

    def save_ai_metadata(
        self,
        content_id: str,
        tags: list[str],
        category: str,
        translated_title: str | None = None,
    ) -> None:
        """AI 요약에서 생성된 tags·category·translated_title을 contents 테이블에 UPDATE한다."""
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE contents
                       SET tags = :tags,
                           category = :category,
                           translated_title = :translated_title,
                           updated_at = :now
                     WHERE id = :content_id
                    """),
                {
                    "content_id": content_id,
                    "tags": json.dumps(tags, ensure_ascii=False),
                    "category": category,
                    "translated_title": translated_title,
                    "now": datetime.now(tz=timezone.utc),
                },
            )
        logger.debug(
            "AI metadata 저장 완료: content_id=%s category=%s tags=%s translated_title=%s",
            content_id,
            category,
            tags,
            translated_title,
        )

    def find_by_published_range(self, start: datetime, end: datetime) -> list[dict]:
        """기간 내 발행된 콘텐츠 목록을 반환한다 (KST 기준 >= start AND < end)."""
        with self._engine.begin() as conn:
            result = conn.execute(
                text("""
                    SELECT id, title, translated_title, category, tags,
                           source_id, published_at
                    FROM contents
                    WHERE published_at >= :start AND published_at < :end
                      AND is_available = true
                    ORDER BY published_at DESC
                """),
                {"start": start, "end": end},
            )
            return [dict(row) for row in result.mappings().fetchall()]

    def find_view_counts_by_period(
        self, start: datetime, end: datetime
    ) -> dict[str, int]:
        """기간 내 content_id별 고유 조회수를 반환한다.

        COUNT(DISTINCT user_id) — 동일 유저의 다중 클릭은 1건으로 카운트.
        content_view_logs.created_at 컬럼 기준 (DP-396 BaseCreatedEntity).
        """
        with self._engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT content_id, COUNT(DISTINCT user_id) AS view_count
                    FROM content_view_logs
                    WHERE created_at >= :start AND created_at < :end
                    GROUP BY content_id
                """),
                {"start": start, "end": end},
            ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def close(self) -> None:
        self._engine.dispose()
