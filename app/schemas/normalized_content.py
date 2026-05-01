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
    #: DB `original_content`에 넣지 않고 요약·임베딩 파이프라인에만 넘길 텍스트 (예: Stack Overflow)
    pipeline_body: str | None = None
    is_original_visible: bool = False
    thumbnail_url: str | None = None
    thumbnail_width: int | None = None
    thumbnail_height: int | None = None
    license_type: str | None = None
    # 소스별 참여 지표 (수집 통계용, null for RSS sources)
    likes: int | None = None  # 좋아요/반응수 — Velog likes
    score: int | None = None  # 투표 순점수 — StackOverflow score (찬성-반대, 음수 가능)
    view_count: int | None = None  # 조회수 (SO: view_count)
    comments_count: int | None = None  # 댓글수 (Velog: comments_count)
    # Stack Overflow 전용 필드
    is_answered: bool | None = None
    question_content: str | None = None  # SO 질문 본문 (body_candidate와 별도)
    accepted_answer: dict | None = None  # {"body": str, "score": int}
    top_answers: list[dict] = Field(
        default_factory=list
    )  # [{"body": str, "score": int}]
    # 소스별 추가 데이터 — contents.extra JSONB 컬럼에 저장 (예: YouTube videoId/duration)
    extra: dict | None = None
    # 수집 시 태그 매핑 결과 — content_tags 테이블 INSERT에 사용 (태그 이름 목록)
    content_tags: list[str] = Field(default_factory=list)
