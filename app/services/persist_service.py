"""Service for persisting normalized content into PostgreSQL."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.repositories.content_repository import ContentRepository
from app.repositories.content_source_repository import ContentSourceRepository
from app.schemas.normalized_content import NormalizedContent
from app.schemas.source import SourceConfig

logger = logging.getLogger(__name__)


class PersistService:
    """Coordinates source/content upserts for normalized items."""

    def __init__(
        self,
        source_repository: ContentSourceRepository | None = None,
        content_repository: ContentRepository | None = None,
    ) -> None:
        self.source_repository = source_repository or ContentSourceRepository()
        self.content_repository = content_repository or ContentRepository()

    @staticmethod
    def _resolve_collect_method(source: SourceConfig) -> str:
        if source.content_level == 1:
            return "rss_crawl"
        return "rss"

    def persist_normalized(
        self,
        session: Session,
        *,
        source: SourceConfig,
        normalized_items: Iterable[NormalizedContent],
    ) -> dict[str, int | str]:
        source_row, source_created = self.source_repository.upsert_with_status(
            session,
            name=source.name,
            url=source.site_url,
            collect_method=self._resolve_collect_method(source),
            is_active=source.active,
        )

        saved = 0
        skipped = 0
        inserted = 0
        updated = 0

        for item in normalized_items:
            if not item.canonical_url:
                logger.warning(
                    "Skipping item without canonical_url source=%s entry_external_id=%s",
                    source.name,
                    item.entry_external_id,
                )
                skipped += 1
                continue

            _, created = self.content_repository.upsert_with_status(
                session,
                source_id=source_row.id,
                normalized=item,
                license_type=None,
            )
            saved += 1
            if created:
                inserted += 1
            else:
                updated += 1

        session.commit()

        return {
            "source": source.name,
            "source_upsert_action": "inserted" if source_created else "updated",
            "saved": saved,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
        }
