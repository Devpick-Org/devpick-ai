"""트렌드 분석 결과 Pydantic 스키마 (DP-378)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


class TopContent(BaseModel):
    id: str
    title: str
    translated_title: str | None = None
    source_name: str
    tags: list[str] = []
    view_count: int | None = None
    thumbnail_url: str | None = None
    category: str | None = None
    change_rate: float | None = None


class TrendingTag(BaseModel):
    keyword: str
    count: int
    rank: int
    rank_change: int
    state: str


class TrendResponse(BaseModel):
    unit: str
    period_start: date
    period_end: date
    date_label: str
    top_posts: list[TopContent] = []
    top_posts_summary: str | None = None
    collection_summary: str | None = None
    trending_tags: list[TrendingTag] = []


class TrendGenerateRequest(BaseModel):
    unit: Literal["daily", "weekly", "monthly"]
    scope: str = "global"
    period_start: date | None = None
    force_refresh: bool = False
