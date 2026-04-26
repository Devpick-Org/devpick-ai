"""채용(Epic G) AI 요청/응답 스키마."""

from __future__ import annotations

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
