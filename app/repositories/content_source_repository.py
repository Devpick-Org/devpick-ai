"""Repository for content source upsert operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ContentSource


class ContentSourceRepository:
    """Persists and retrieves content source rows."""

    def upsert_with_status(
        self,
        session: Session,
        *,
        name: str,
        url: str,
        collect_method: str,
        is_active: bool,
    ) -> tuple[ContentSource, bool]:
        """Upsert source and return (row, created)."""
        existing = session.execute(
            select(ContentSource).where(ContentSource.name == name)
        ).scalar_one_or_none()
        if existing is None:
            source = ContentSource(
                name=name,
                url=url,
                collect_method=collect_method,
                is_active=is_active,
            )
            session.add(source)
            session.flush()
            return source, True

        existing.url = url
        existing.collect_method = collect_method
        existing.is_active = is_active
        session.flush()
        return existing, False

    def upsert(
        self,
        session: Session,
        *,
        name: str,
        url: str,
        collect_method: str,
        is_active: bool,
    ) -> ContentSource:
        source, _ = self.upsert_with_status(
            session,
            name=name,
            url=url,
            collect_method=collect_method,
            is_active=is_active,
        )
        return source
