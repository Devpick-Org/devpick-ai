"""AI 요약 입출력 스키마 (Confluence AI 기능 명세서 확정본)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SectionSummary(BaseModel):
    """소제목별 요약 항목."""

    heading: str  # 소제목 (원문 heading 활용 또는 AI 자체 생성)
    content: str  # 해당 섹션의 핵심 요약 (2~4줄)


# ── 4레벨 동시 생성 스키마 (DP-300) ──────────────────────────────────────────


class CommonSummary(BaseModel):
    """콘텐츠 자체 속성 — 레벨 무관 공통 필드."""

    one_line_summary: str
    keywords: list[str]
    category: str
    tags: list[str]
    difficulty: Literal["easy", "medium", "hard"]


class LevelSummary(BaseModel):
    """레벨별 차별화 필드."""

    core_summary: list[SectionSummary] = Field(min_length=1)
    key_points: list[str]
    study_questions: list[str]
    next_recommendation: str
    confidence: float = Field(ge=0.0, le=1.0)


class AllLevelsSummaryRequest(BaseModel):
    """4레벨 동시 요약 요청 스키마."""

    content_id: str
    text: str = Field(min_length=1)  # HTML 본문
    thumbnail_url: str | None = None


class AllLevelsSummaryResponse(BaseModel):
    """4레벨 동시 요약 응답 스키마."""

    content_id: str
    common: CommonSummary
    beginner: LevelSummary
    junior: LevelSummary
    mid: LevelSummary
    senior: LevelSummary
    generated_at: str  # ISO 8601
    thumbnail_url: str | None = None
