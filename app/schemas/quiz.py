"""AI 퀴즈 생성 요청/응답 스키마 (DP-265)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QuizOption(BaseModel):
    """객관식 선지."""

    id: str   # "A" ~ "E"
    text: str


class QuizQuestion(BaseModel):
    """퀴즈 문제 한 개."""

    type: Literal["multiple_choice", "short_answer"]
    question: str
    options: list[QuizOption]
    correct_option_id: str  # 객관식: "A"~"E", 주관식: ""
    explanation: str


class LevelQuiz(BaseModel):
    """레벨별 퀴즈 3문제."""

    questions: list[QuizQuestion]


class QuizRequest(BaseModel):
    """POST /internal/quiz 요청 스키마."""

    content_id: str = Field(min_length=1)
    text: str = Field(min_length=1, description="원문 HTML 또는 텍스트")
    user_id: str | None = None


class AllLevelsQuizResponse(BaseModel):
    """POST /internal/quiz 응답 스키마 — 4레벨 동시 생성."""

    content_id: str
    quiz_id: str
    beginner: LevelQuiz
    junior: LevelQuiz
    mid: LevelQuiz
    senior: LevelQuiz
    generated_at: str
