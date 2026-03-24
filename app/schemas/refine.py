"""AI 질문 개선 입출력 스키마 (DP-231)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RefineRequest(BaseModel):
    """질문 개선 요청 스키마 — 백엔드 QuestionRefineRequest 대응."""

    title: str = Field(min_length=1)  # 질문 제목 (Post.title)
    content: str = Field(min_length=1)  # 질문 본문 (Post.content)
    content_id: str | None = None  # optional — 관련 아티클 ID (MongoDB 청크 조회용)
    user_id: str | None = None  # 이벤트 로그용 (DP-252) — 없으면 로깅 스킵


class RefineResponse(BaseModel):
    """질문 개선 결과 응답 스키마 — LLM 응답 계약."""

    refined_title: str  # 개선된 질문 제목 (1줄)
    refined_content: str  # 개선된 질문 본문
    suggested_tags: list[str]  # 추천 태그 2~5개
    confidence: float = Field(ge=0.0, le=1.0)  # 개선 품질 자체 평가
    generated_at: str  # ISO 8601
