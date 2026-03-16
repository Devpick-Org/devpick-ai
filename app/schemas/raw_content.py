"""Raw feed and entry schemas for source-level collection output."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RawFeedMeta(BaseModel):
    """Feed-level raw metadata from a single fetch."""

    source_name: str
    feed_url: str
    site_url: str
    parser_type: str
    http_status: int
    fetched_at: datetime = Field(default_factory=utc_now)
    response_hash: str
    etag: str | None = None
    last_modified: str | None = None
    title: str | None = None
    link: str | None = None
    description: str | None = None


class RawEntry(BaseModel):
    """Single raw entry preserving as much source data as possible."""

    source_name: str
    feed_url: str
    site_url: str
    parser_type: str
    content_level_hint: int
    entry_external_id: str
    entry_url: str | None = None
    title_raw: str | None = None
    author_raw: str | None = None
    published_at_raw: str | None = None
    summary_raw: str | None = None
    content_raw: str | None = None
    html_body_raw: str | None = None
    html_text_raw: str | None = None
    thumbnail_url: str | None = None
    categories_raw: list[str] = Field(default_factory=list)
    raw_xml_fragment: str | None = None
    fetched_at: datetime = Field(default_factory=utc_now)
    response_hash: str
    parser_version: str = "rss-raw-v1"
    entry_hash: str
