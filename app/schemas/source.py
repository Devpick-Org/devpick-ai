"""Source configuration schema for RSS/Atom raw collection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    """Config for one feed source in ingestion pipeline."""

    name: str
    feed_url: str
    site_url: str
    parser_type: Literal["rss", "atom", "auto", "backfill"] = "auto"
    content_level: int = Field(default=2, ge=1)
    active: bool = True
    note: str = ""
    # 콘텐츠 관련성 필터 (소스별 설정)
    url_include_pattern: str | None = None  # 이 패턴 포함 URL만 허용 (None = 전체 허용)
    title_blocklist: list[str] = Field(default_factory=list)  # 제목에 포함 시 제외
