"""AI 요약 출력 스키마 (Confluence AI 기능 명세서 확정본)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SummaryResponse(BaseModel):
    """LLM 요약 결과 응답 스키마."""

    content_id: str
    level: Literal["junior", "mid", "senior"]
    one_line_summary: str
    core_summary: str
    key_points: list[str]
    keywords: list[str]
    difficulty: Literal["easy", "medium", "hard"]
    next_recommendation: str
    study_questions: list[str]
    confidence: float  # 0.0 ~ 1.0
    generated_at: str  # ISO 8601
