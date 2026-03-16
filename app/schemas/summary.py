"""AI 요약 출력 스키마 (Confluence AI 기능 명세서 확정본)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SectionSummary(BaseModel):
    """소제목별 요약 항목."""

    heading: str  # 소제목 (원문 heading 활용 또는 AI 자체 생성)
    content: str  # 해당 섹션의 핵심 요약 (2~4줄)


class SummaryResponse(BaseModel):
    """LLM 요약 결과 응답 스키마."""

    content_id: str
    level: Literal["junior", "mid", "senior"]
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
