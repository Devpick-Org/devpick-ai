"""채용(Epic G) AI 요청/응답 스키마."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ParseJdRequest(BaseModel):
    raw_jd_text: str = Field(..., min_length=1)


class ParseJdResponse(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    skip_reason: str | None = None


class InterviewQaRequest(BaseModel):
    job_title: str
    company_name: str
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    resume_json: str


class SkillGapRequest(BaseModel):
    missing_skills: list[str] = Field(default_factory=list)
    job_title: str = ""
    company_name: str = ""
    resume_json: str = "{}"


class SkillGapResponse(BaseModel):
    roadmap: list[str] = Field(default_factory=list)


class ResumeParseRequest(BaseModel):
    """Spring에서 PDF/DOCX 추출 텍스트를 받아 마스터 이력서 JSON 생성."""

    file_name: str = ""
    text: str = Field(..., min_length=1)
    profile_hint: str | None = None


class ResumeEnrichRequest(BaseModel):
    """1차 파싱 결과를 바탕으로 비어 있는 summary·경력·프로젝트 등만 채운 패치 생성."""

    file_name: str = ""
    text: str = Field(..., min_length=1)
    partial_resume: dict[str, Any] | str = Field(
        ...,
        description="1차 정규화 직후 이력서 JSON 객체 또는 JSON 문자열",
    )


# ─────────────────────────────────────────────
# Mock Interview (DP — 채팅형 모의면접)
# ─────────────────────────────────────────────


class MockInterviewQuestionPlanItem(BaseModel):
    questionNo: int = Field(..., ge=1, le=15)
    phase: str
    topic: str
    prompt: str
    jdOnlyKeyword: bool = False
    keywords: list[str] = Field(default_factory=list)


class MockInterviewPlan(BaseModel):
    questions: list[MockInterviewQuestionPlanItem] = Field(default_factory=list)
    coreCsTopics: list[str] = Field(default_factory=list)
    extendedCsTopics: list[str] = Field(default_factory=list)
    jdGapKeywords: list[str] = Field(default_factory=list)
    domainLabel: str = ""


class MockInterviewPlanRequest(BaseModel):
    job_title: str
    company_name: str = ""
    job_category: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    resume_json: str = "{}"
    jd_context: str = ""
    base_plan: MockInterviewPlan
    model_key: str = "balanced"


class MockInterviewTurnHistoryItem(BaseModel):
    type: str
    content: str
    rating: str | None = None


class MockInterviewTurnRequest(BaseModel):
    session_id: str | None = None
    model_key: str = "balanced"
    job_title: str = ""
    company_name: str = ""
    job_category: str | None = None
    question_no: int
    phase: str
    question_topic: str = ""
    question_prompt: str = ""
    question_keywords: list[str] = Field(default_factory=list)
    answer: str
    transcript: list[MockInterviewTurnHistoryItem] = Field(default_factory=list)
    plan_summary: dict = Field(default_factory=dict)


class MockInterviewTurnResponse(BaseModel):
    rating: str = "OK"
    evaluator_comment: str = ""
    decision: str = "next"
    follow_up_question: str | None = None
    retry_hint: str | None = None
    next_question_prompt: str | None = None


class MockInterviewFinalizeTurn(BaseModel):
    orderNo: int = 0
    questionNo: int = 0
    phase: str = ""
    type: str = ""
    content: str = ""
    rating: str | None = None


class MockInterviewFinalizeRequest(BaseModel):
    session_id: str | None = None
    model_key: str = "balanced"
    job_title: str = ""
    company_name: str = ""
    job_category: str | None = None
    answered_count: int = 0
    total_questions: int = 15
    early_finished: bool = False
    plan: MockInterviewPlan
    turns: list[MockInterviewFinalizeTurn] = Field(default_factory=list)


class MockInterviewScoreSet(BaseModel):
    framework: int | None = None
    design: int | None = None
    problemSolving: int | None = None
    csInfra: int | None = None
    communication: int | None = None


class MockInterviewPerQuestionFeedback(BaseModel):
    questionNo: int
    questionSummary: str = ""
    answerSummary: str = ""
    modelAnswer: str = ""
    whyImportant: str = ""
    learningDirection: str = ""
    references: list[str] = Field(default_factory=list)
    rating: str | None = None
    passed: bool = False


class MockInterviewFinalizeResponse(BaseModel):
    scores: MockInterviewScoreSet
    overallScore: int | None = None
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    actionItems: list[str] = Field(default_factory=list)
    uncoveredKeywords: list[str] = Field(default_factory=list)
    perQuestion: list[MockInterviewPerQuestionFeedback] = Field(default_factory=list)
    notice: str | None = None
