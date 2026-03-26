"""4레벨 동시 AI 요약 프롬프트 + Tool Use 스키마 (DP-300)."""

from __future__ import annotations

SYSTEM_PROMPT_ALL_LEVELS = """\
당신은 개발자를 위한 기술 콘텐츠 요약 전문가입니다.
주어진 글을 분석하고, save_all_summaries 도구를 호출하여 결과를 저장하세요.
모든 필드는 한국어로 작성하되, 기술 용어(라이브러리명, API명 등)는 원어 그대로 사용하세요.

## 구조

### common (공통 필드 — 레벨 무관)
- one_line_summary: 글의 핵심을 한 문장(50자 이내)으로 요약. "~하는 방법", "~의 원리" 같은 명사형 종결
- keywords: 본문에 실제 등장하는 핵심 용어/개념 3~7개. 예: "캐시 무효화", "TTL". tags와 겹치지 않게 (keywords=개념, tags=기술 스택)
- tags: 글의 기술 스택/주제 카테고리 2~5개. 예: "Java", "Spring Boot", "백엔드". 버전 번호 제외
- difficulty: easy(입문자도 이해 가능) / medium(실무 경험 필요) / hard(깊은 도메인 지식 필요)

### beginner / junior / mid / senior (레벨별 필드)
각 레벨은 독립적인 독자를 대상으로 작성하세요:

- beginner: 완전 입문자. 배경지식 없이도 이해 가능한 수준. 모든 용어에 설명 병기
- junior: 초급 개발자. 비유/예시로 쉽게. '왜 중요한지' 맥락 포함
- mid: 중급 실무자. 실무 적용/패턴/장단점 중심
- senior: 시니어/아키텍트. 트레이드오프/확장성/한계점까지 분석

각 레벨 공통 필드:
- core_summary: 소제목 단위로 핵심 내용 요약 (레벨별 관점 차이 반영). heading은 원문 소제목 또는 AI 생성. content는 2~4줄
- key_points: 해당 레벨 독자에게 중요한 포인트 3~5개
- study_questions: 해당 레벨에 맞는 이해/적용 점검 질문 3~5개
- next_recommendation: 이 글 다음에 학습할 주제 1가지. "~에 대해 알아보세요" 형태
- confidence: 요약 품질 자체 평가 0.0~1.0 (1.0=전문 분야/구조 명확, 0.7=일반 기술 글, 0.7 미만=짧거나 모호)
"""

_LEVEL_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "core_summary": {
            "type": "array",
            "description": "소제목별 요약",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["heading", "content"],
            },
        },
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "핵심 포인트 3~5개",
        },
        "study_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "학습 점검 질문 3~5개",
        },
        "next_recommendation": {
            "type": "string",
            "description": "다음 학습 추천 주제",
        },
        "confidence": {
            "type": "number",
            "description": "요약 품질 자체 평가 0.0~1.0",
        },
    },
    "required": [
        "core_summary",
        "key_points",
        "study_questions",
        "next_recommendation",
        "confidence",
    ],
}

SUMMARY_ALL_LEVELS_TOOL = {
    "name": "save_all_summaries",
    "description": "4개 레벨(beginner/junior/mid/senior) 요약 결과를 한번에 저장합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "common": {
                "type": "object",
                "description": "레벨 무관 공통 필드",
                "properties": {
                    "one_line_summary": {
                        "type": "string",
                        "description": "50자 이내 한줄 요약",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "본문 핵심 용어 3~7개",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "기술 스택/카테고리 2~5개",
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                    },
                },
                "required": ["one_line_summary", "keywords", "tags", "difficulty"],
            },
            "beginner": _LEVEL_SUMMARY_SCHEMA,
            "junior": _LEVEL_SUMMARY_SCHEMA,
            "mid": _LEVEL_SUMMARY_SCHEMA,
            "senior": _LEVEL_SUMMARY_SCHEMA,
        },
        "required": ["common", "beginner", "junior", "mid", "senior"],
    },
}


def build_user_prompt_all_levels(text: str) -> str:
    """4레벨 동시 생성용 사용자 프롬프트를 생성한다.

    Args:
        text: 전처리된 아티클 텍스트

    Raises:
        ValueError: 빈 text
    """
    if not text:
        raise ValueError("요약할 텍스트가 없습니다")
    return f"아래 기술 글을 beginner/junior/mid/senior 4개 레벨로 동시에 요약하세요.\n\n---\n\n{text}"
