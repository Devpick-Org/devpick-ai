"""SQLAlchemy ORM models for normalized content persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class ContentSource(Base):
    """Content source registry."""

    __tablename__ = "content_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    url: Mapped[str] = mapped_column(String(500))
    collect_method: Mapped[str] = mapped_column(String(50), default="rss")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    contents: Mapped[list["Content"]] = relationship(back_populates="source")


class Content(Base):
    """Normalized content records."""

    __tablename__ = "contents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("content_sources.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    canonical_url: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    original_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_original_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    license_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    source: Mapped[ContentSource] = relationship(back_populates="contents")
