"""AI 퀴즈 생성 프롬프트 + Tool Use 스키마 (DP-265)."""

from __future__ import annotations

SYSTEM_PROMPT_QUIZ = """\
당신은 개발자 학습을 돕는 기술 블로그 퀴즈 출제 전문가입니다.
주어진 글을 분석하고, save_quiz 도구를 호출하여 4개 레벨(beginner · junior · mid · senior)별 퀴즈를 저장하세요.

## 공통 출제 원칙

총 3문제를 출제하세요:
- 1번·2번: 객관식 5지선다 (multiple_choice) — 선지는 반드시 5개
- 3번: 주관식 단답형 (short_answer) — 10단어 이내로 답할 수 있는 명확한 정답이 존재하는 문제

- 글의 핵심 개념·원리를 검증하는 문제를 출제하세요. 사소한 세부 수치나 예시는 피하세요.
- 4개 레벨은 같은 핵심 개념을 다루되, 용어와 표현 방식만 레벨에 맞게 조정하세요.
- 객관식 오답 선지는 그럴듯하게 작성하세요 (단순 엉터리 오답 금지).
- 객관식 정답은 correct_option_id에 "A"~"E" 중 하나를 입력하세요. 주관식은 빈 문자열("")로 입력하세요.
- 주관식 답은 단어 또는 짧은 구절이어야 합니다. 문장형 정답은 출제하지 마세요.
- 문제 순서는 반드시 1번·2번 객관식, 3번 주관식 순서를 지키세요.
- 모든 문제는 한국어로 작성하되, 기술 용어(라이브러리명, API명 등)는 원어 그대로 사용하세요.

## 레벨별 용어·표현 기준

**beginner**: 기술 용어가 처음 등장할 때 괄호 안에 짧은 설명을 추가하세요.
예: "캐시(자주 쓰는 데이터를 빠르게 꺼낼 수 있도록 임시 저장하는 공간)".
선지와 explanation도 쉬운 말로 풀어서 작성하고, 개념을 처음 접하는 사람도 이해할 수 있게 비유나 예시를 포함하세요.

**junior**: 기본 기술 용어는 그대로 사용하되, 생소할 수 있는 개념은 한 문장 이내로 짧게 부연하세요.
explanation은 왜 그 답이 맞는지 원리 위주로 설명하세요.

**mid**: 표준 기술 용어를 그대로 사용하세요.
explanation은 핵심만 간결하게 작성하세요.

**senior**: 전문 용어와 약어를 자유롭게 사용하세요.
explanation에는 트레이드오프나 심화 내용을 포함해 간결하게 작성하세요.
"""

_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "description": "퀴즈 문제 배열. 순서: [객관식, 객관식, 주관식]",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["multiple_choice", "short_answer"],
                    },
                    "question": {"type": "string", "description": "문제 내용"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "description": "선지 ID (A~E)"},
                                "text": {"type": "string", "description": "선지 내용"},
                            },
                            "required": ["id", "text"],
                        },
                        "description": "객관식 5개 선지 [{id, text}]. 주관식이면 빈 배열 []",
                    },
                    "correct_option_id": {
                        "type": "string",
                        "description": "정답 선지 ID (A~E). 주관식이면 빈 문자열 \"\"",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "정답 이유 설명 (2~3문장)",
                    },
                },
                "required": ["type", "question", "options", "correct_option_id", "explanation"],
            },
        }
    },
    "required": ["questions"],
}

QUIZ_TOOL = {
    "name": "save_quiz",
    "description": "4개 레벨(beginner·junior·mid·senior)별 퀴즈 3문제(객관식 2 + 주관식 1)를 저장합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "beginner": _QUESTIONS_SCHEMA,
            "junior": _QUESTIONS_SCHEMA,
            "mid": _QUESTIONS_SCHEMA,
            "senior": _QUESTIONS_SCHEMA,
        },
        "required": ["beginner", "junior", "mid", "senior"],
    },
}


def build_user_prompt(text: str) -> str:
    """퀴즈 생성용 사용자 프롬프트를 생성한다.

    Args:
        text: 전처리된 아티클 텍스트

    Raises:
        ValueError: 빈 text
    """
    if not text:
        raise ValueError("퀴즈를 생성할 텍스트가 없습니다")
    return (
        "아래 기술 블로그 글을 읽고, 핵심 내용을 검증하는 퀴즈 3문제를 "
        "4개 레벨(beginner·junior·mid·senior)로 출제하세요.\n"
        "1번·2번은 객관식 5지선다, 3번은 주관식 단답형으로 출제하세요.\n"
        "각 레벨은 같은 핵심 개념을 다루되, 용어와 표현 방식만 레벨에 맞게 조정하세요.\n\n"
        "---\n\n"
        f"{text}"
    )
