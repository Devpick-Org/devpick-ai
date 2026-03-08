"""Repository for normalized content upsert operations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Content
from app.schemas.normalized_content import NormalizedContent


def parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class ContentRepository:
    """Persists and retrieves normalized content rows."""

    def upsert_with_status(
        self,
        session: Session,
        *,
        source_id: int,
        normalized: NormalizedContent,
        license_type: str | None = None,
    ) -> tuple[Content, bool]:
        """Upsert content and return (row, created)."""
        if not normalized.canonical_url:
            raise ValueError("canonical_url is required for content upsert")

        existing = session.execute(
            select(Content).where(Content.canonical_url == normalized.canonical_url)
        ).scalar_one_or_none()

        metadata_json = {
            "content_kind": normalized.content_kind,
            "body_source": normalized.body_source,
            "entry_external_id": normalized.entry_external_id,
        }

        if existing is None:
            content = Content(
                source_id=source_id,
                title=normalized.title,
                canonical_url=normalized.canonical_url,
                preview=normalized.preview,
                published_at=parse_published_at(normalized.published_at),
                original_content=normalized.body_candidate,
                is_original_visible=False,
                license_type=license_type,
                metadata_json=metadata_json,
            )
            session.add(content)
            session.flush()
            return content, True

        existing.source_id = source_id
        existing.title = normalized.title
        existing.preview = normalized.preview
        existing.published_at = parse_published_at(normalized.published_at)
        existing.original_content = normalized.body_candidate
        existing.is_original_visible = False
        existing.license_type = license_type
        existing.metadata_json = metadata_json
        session.flush()
        return existing, False

    def upsert(
        self,
        session: Session,
        *,
        source_id: int,
        normalized: NormalizedContent,
        license_type: str | None = None,
    ) -> Content:
        content, _ = self.upsert_with_status(
            session,
            source_id=source_id,
            normalized=normalized,
            license_type=license_type,
        )
        return content
