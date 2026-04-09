"""Minimum normalized content schema from raw RSS entries."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NormalizedContent(BaseModel):
    """Normalized content view derived from a single raw entry."""

    source_name: str
    title: str | None = None
    author: str | None = None
    canonical_url: str | None = None
    published_at: str | None = None
    preview: str | None = None
    body_candidate: str | None = None
    is_original_visible: bool = False
    thumbnail_url: str | None = None
    license_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    # 소스별 참여 지표 (수집 통계용, null for RSS sources)
    likes: int | None = None  # 좋아요/추천수 (Velog: likes, SO: score)
    view_count: int | None = None  # 조회수 (SO: view_count)
    comments_count: int | None = None  # 댓글수 (Velog: comments_count)
    # Stack Overflow 전용 필드
    is_answered: bool | None = None
    question_content: str | None = None  # SO 질문 본문 (body_candidate와 별도)
    accepted_answer: dict | None = None  # {"body": str, "score": int}
    top_answers: list[dict] = Field(default_factory=list)  # [{"body": str, "score": int}]
