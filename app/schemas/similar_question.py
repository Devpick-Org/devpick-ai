"""유사 질문 탐색 입출력 스키마 (DP-235)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SimilarQuestionRequest(BaseModel):
    """유사 질문 검색 요청 스키마 — 백엔드 SimilarQuestionRequest 대응."""

    text: str = Field(
        min_length=1
    )  # 검색 텍스트 (refined_title + " " + refined_content)
    question_id: str | None = None  # 자기 자신 제외용
    top_k: int = Field(default=5, ge=1, le=20)  # 반환할 최대 유사 질문 수


class SimilarQuestion(BaseModel):
    """유사 질문 개별 항목."""

    question_id: str  # 유사 질문 ID (FAISS ChunkMetadata.content_id)
    text: str  # 유사 질문 텍스트
    score: float = Field(ge=0.0, le=1.0)  # 유사도 점수
    tags: list[str]  # 추천 태그 (ChunkMetadata.tags)


class SimilarQuestionResponse(BaseModel):
    """유사 질문 검색 결과 응답 스키마."""

    results: list[SimilarQuestion]  # 유사 질문 리스트 (유사도 내림차순)
    total: int  # 반환된 결과 수
