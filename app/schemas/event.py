"""AI 처리 이벤트 타입 정의 (DP-252)."""

from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    """AI 서버에서 발생하는 처리 이벤트 유형."""

    SUMMARY_GENERATED = "SUMMARY_GENERATED"  # POST /internal/summary
    ALL_LEVELS_SUMMARY_GENERATED = (
        "ALL_LEVELS_SUMMARY_GENERATED"  # POST /internal/summaries
    )
    QUESTION_REFINED = "QUESTION_REFINED"  # POST /internal/refine
    ANSWER_GENERATED = "ANSWER_GENERATED"  # POST /internal/answer
    SIMILAR_QUESTIONS_SEARCHED = (
        "SIMILAR_QUESTIONS_SEARCHED"  # POST /internal/similar-questions
    )
    INSIGHT_GENERATED = "INSIGHT_GENERATED"  # POST /internal/report
