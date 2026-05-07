"""리포트 키워드 분석 서비스 — kiwipiepy + TF-IDF (DP-459)."""

from __future__ import annotations

from app.schemas.report_keywords import (
    ContentItem,
    ContentKeywordsResponse,
    KeywordCount,
    QuestionItem,
    QuestionKeywordsResponse,
)
from app.services.trend.tfidf import TfidfAnalyzer
from app.services.trend.tokenizer import KoreanTokenizer

_TOP_CONTENT_KEYWORDS = 10
_TOP_QUESTION_KEYWORDS = 5


class ReportKeywordsService:

    def __init__(self) -> None:
        self._tokenizer = KoreanTokenizer()
        self._analyzer = TfidfAnalyzer(top_n=_TOP_CONTENT_KEYWORDS, min_df=1)
        self._q_analyzer = TfidfAnalyzer(top_n=_TOP_QUESTION_KEYWORDS, min_df=1)

    def extract_content_keywords(
        self, contents: list[ContentItem]
    ) -> ContentKeywordsResponse:
        if not contents:
            return ContentKeywordsResponse(keywords=[])

        raw_texts = [f"{c.title} {c.preview} {' '.join(c.tags)}" for c in contents]
        tokenized = self._tokenizer.tokenize(raw_texts)
        ranked = self._analyzer.extract(tokenized)

        keywords = [
            KeywordCount(keyword=term, count=max(1, round(score)))
            for term, score in ranked
        ]
        return ContentKeywordsResponse(keywords=keywords)

    def extract_question_keywords(
        self,
        tech_questions: list[QuestionItem],
        career_questions: list[QuestionItem],
    ) -> QuestionKeywordsResponse:
        return QuestionKeywordsResponse(
            tech_keywords=self._extract_from_questions(tech_questions),
            career_keywords=self._extract_from_questions(career_questions),
        )

    def _extract_from_questions(self, questions: list[QuestionItem]) -> list[str]:
        if not questions:
            return []
        raw_texts = [f"{q.title} {q.content} {q.adopted_answer}" for q in questions]
        tokenized = self._tokenizer.tokenize(raw_texts)
        ranked = self._q_analyzer.extract(tokenized)
        return [term for term, _ in ranked]
