"""AI 주간 인사이트 입출력 스키마 (DP-259)."""

from __future__ import annotations

from pydantic import BaseModel


class TagCount(BaseModel):
    """태그별 활동 카운트 (top_tags용)."""

    tag: str
    count: int


class DailyActivity(BaseModel):
    """요일별 활동 카운트."""

    day_of_week: str  # MON~SUN
    count: int


class TagActivity(BaseModel):
    """레이더 차트용 태그별 활동 카운트."""

    tag_name: str
    count: int


class ActivityData(BaseModel):
    """백엔드가 전달하는 주간 활동 집계.

    모든 필드는 optional (기본값 제공) — 백엔드 버전 차이에도 하위호환.
    """

    contents_read: int = 0
    questions_created: int = 0
    scraps_count: int = 0
    top_tags: list[TagCount] = []
    daily_activities: list[DailyActivity] = []
    tag_activities: list[TagActivity] = []
    read_content_ids: list[str] = []  # 조회한 글 ID 목록
    scrapped_content_ids: list[str] = []  # 스크랩한 글 ID 목록 (가중치 높음)
    question_ids: list[str] = []  # 작성한 질문 ID 목록


class InsightRequest(BaseModel):
    """POST /internal/report 요청 스키마."""

    report_id: str
    user_id: str
    week_start: str  # ISO date (2026-03-17)
    week_end: str  # ISO date (2026-03-23)
    activities: ActivityData


class InsightResponse(BaseModel):
    """POST /internal/report 응답 스키마.

    MongoDB weekly_report_insights 필드와 1:1 대응:
    report_id, well_done, lacking, next_week, generated_at
    """

    report_id: str
    well_done: str  # 이번 주 잘한 점
    lacking: str  # 아쉬운 점
    next_week: str  # 다음 주 추천 방향
    generated_at: str  # ISO 8601
