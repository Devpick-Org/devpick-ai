"""리포트 키워드 분석 입출력 스키마 (DP-459)."""

from __future__ import annotations

from pydantic import BaseModel


class ContentItem(BaseModel):
    content_id: str
    title: str
    preview: str = ""
    tags: list[str] = []


class ContentKeywordsRequest(BaseModel):
    contents: list[ContentItem]


class KeywordCount(BaseModel):
    keyword: str
    count: int


class ContentKeywordsResponse(BaseModel):
    keywords: list[KeywordCount]


class QuestionItem(BaseModel):
    title: str
    content: str = ""
    adopted_answer: str = ""


class QuestionKeywordsRequest(BaseModel):
    tech_questions: list[QuestionItem] = []
    career_questions: list[QuestionItem] = []


class QuestionKeywordsResponse(BaseModel):
    tech_keywords: list[str]
    career_keywords: list[str]
