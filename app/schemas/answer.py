"""AI 1차 답변 입출력 스키마 (DP-234)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnswerRequest(BaseModel):
    """AI 답변 요청 스키마 — 백엔드 AnswerRequest 대응."""

    refined_title: str = Field(
        min_length=1
    )  # 개선된 질문 제목 (RefineResponse.refined_title)
    refined_content: str = Field(
        min_length=1
    )  # 개선된 질문 본문 (RefineResponse.refined_content)
    original_title: str | None = None  # 원본 질문 제목 (사용자 이해 수준 파악용)
    original_content: str | None = None  # 원본 질문 본문
    suggested_tags: list[str] | None = (
        None  # Refine 추천 태그 (RefineResponse.suggested_tags)
    )
    content_id: str | None = None  # 관련 아티클 ID (MongoDB 청크 조회용)
    question_id: str | None = None  # 질문 식별자 — MongoDB 저장 키


class RelatedContent(BaseModel):
    """답변이 참고한 기술 블로그 항목."""

    content_id: str  # 참고한 글의 ID
    one_line_summary: str  # ai_summaries에서 조회한 한 줄 요약


class AnswerResponse(BaseModel):
    """AI 답변 결과 응답 스키마 — LLM 응답 계약."""

    answer_content: str  # 마크다운 형식 답변
    key_points: list[str]  # 핵심 포인트 2~5개
    suggested_tags: list[str]  # 기술 스택 태그 2~5개
    related_contents: list[RelatedContent] = []  # 참고한 기술 블로그 (라우터가 주입)
    confidence: float = Field(ge=0.0, le=1.0)  # 답변 품질 자체 평가
    generated_at: str  # ISO 8601
