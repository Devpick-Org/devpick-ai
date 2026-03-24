"""AI 요약 입출력 스키마 (Confluence AI 기능 명세서 확정본)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SummaryRequest(BaseModel):
    """콘텐츠 AI 요약 요청 스키마."""

    content_id: str
    level: str  # JUNIOR/MIDDLE/SENIOR 또는 junior/mid/senior
    text: str = Field(min_length=1)  # HTML 본문 (빈 문자열 → 422 자동 거부)
    thumbnail_url: str | None = None
    user_id: str | None = None  # 이벤트 로그용 (DP-252) — 없으면 로깅 스킵


class SectionSummary(BaseModel):
    """소제목별 요약 항목."""

    heading: str  # 소제목 (원문 heading 활용 또는 AI 자체 생성)
    content: str  # 해당 섹션의 핵심 요약 (2~4줄)


class SummaryResponse(BaseModel):
    """LLM 요약 결과 응답 스키마."""

    content_id: str
    level: Literal["beginner", "junior", "mid", "senior"]
    one_line_summary: str
    core_summary: list[SectionSummary] = Field(min_length=1)
    key_points: list[str]
    keywords: list[str]
    tags: list[str]  # AI 추출 기술 카테고리 (Java, Spring Boot, Docker 등)
    difficulty: Literal["easy", "medium", "hard"]
    next_recommendation: str
    study_questions: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    generated_at: str  # ISO 8601
    thumbnail_url: str | None = None  # 호출자 주입, AI 생성 아님


# ── 4레벨 동시 생성 스키마 (DP-300) ──────────────────────────────────────────


class CommonSummary(BaseModel):
    """콘텐츠 자체 속성 — 레벨 무관 공통 필드."""

    one_line_summary: str
    keywords: list[str]
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
    user_id: str | None = None  # 이벤트 로그용 (DP-252) — 없으면 로깅 스킵


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
