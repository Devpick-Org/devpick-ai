"""AI 퀴즈 생성 요청/응답 스키마 (DP-265)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class QuizOption(BaseModel):
    """객관식 선지."""

    id: str  # "A" ~ "E"
    text: str


class QuizQuestion(BaseModel):
    """퀴즈 문제 한 개."""

    id: str = ""  # "q1"~"q3" — 서비스 코드에서 주입, LLM 미생성
    type: Literal["multiple_choice", "short_answer"]
    question: str
    options: list[QuizOption]
    correct_option_id: str  # 객관식: "A"~"E", 주관식: ""
    explanation: str
    # 주관식 단답 정답(자동 채점용). 객관식은 반드시 "".
    correct_answer: str = ""

    @model_validator(mode="after")
    def validate_answer_fields(self) -> QuizQuestion:
        if self.type == "multiple_choice":
            if self.correct_answer.strip():
                raise ValueError("multiple_choice 문항은 correct_answer가 빈 문자열이어야 합니다")
        elif self.type == "short_answer":
            if not self.correct_answer.strip():
                raise ValueError("short_answer 문항은 correct_answer에 단답 정답이 필요합니다")
            if self.correct_option_id.strip():
                raise ValueError("short_answer 문항은 correct_option_id가 빈 문자열이어야 합니다")
        return self


class LevelQuiz(BaseModel):
    """레벨별 퀴즈 3문제."""

    questions: list[QuizQuestion]
    passing_count: int = 2  # 고정값 (3문제 중 2개 이상 정답 = 통과), LLM 미생성
    estimated_minutes: int  # LLM 생성 — 레벨별 예상 풀이 시간(분)


class QuizRequest(BaseModel):
    """POST /internal/quiz 요청 스키마."""

    content_id: str = Field(min_length=1)
    text: str = Field(min_length=1, description="원문 HTML 또는 텍스트")
    user_id: str | None = None


class AllLevelsQuizResponse(BaseModel):
    """POST /internal/quiz 응답 스키마 — 4레벨 동시 생성."""

    content_id: str
    quiz_id: str
    title: str  # LLM 생성 — 글의 핵심 주제를 담은 퀴즈 제목
    beginner: LevelQuiz
    junior: LevelQuiz
    mid: LevelQuiz
    senior: LevelQuiz
    generated_at: str
