"""AI 퀴즈 생성 프롬프트 + Tool Use 스키마 (DP-265)."""

from __future__ import annotations

SYSTEM_PROMPT_QUIZ = """\
당신은 개발자 학습을 돕는 기술 블로그 퀴즈 출제 전문가입니다.
주어진 글을 분석하고, save_quiz 도구를 호출하여 퀴즈 제목과 4개 레벨(beginner · junior · mid · senior)별 퀴즈를 저장하세요.

## 퀴즈 제목 (title)

글의 핵심 주제를 담은 퀴즈 제목을 20자 이내 한국어로 작성하세요.
예: "Redis 캐시 전략의 핵심", "Spring AOP 동작 원리"
기술 용어(라이브러리명, 프레임워크명 등)는 원어 그대로 사용하세요.

## 공통 출제 원칙

총 3문제를 출제하세요:
- 1번·2번: 객관식 5지선다 (multiple_choice) — 선지는 반드시 5개
- 3번: 주관식 단답형 (short_answer) — 10단어 이내로 답할 수 있는 명확한 정답이 존재하는 문제

- 글의 핵심 개념·원리를 검증하는 문제를 출제하세요. 사소한 세부 수치나 예시는 피하세요.
- 객관식 오답 선지는 그럴듯하게 작성하세요 (단순 엉터리 오답 금지).
- 객관식 정답은 correct_option_id에 "A"~"E" 중 하나를 입력하고, correct_answer는 반드시 빈 문자열("")로 두세요.
- 주관식은 correct_option_id를 빈 문자열("")로 두고, 자동 채점용 모범 답은 correct_answer에만 넣으세요(단어 또는 짧은 구절, 10단어 이내). explanation은 해설이며 정답 텍스트와 구분합니다.
- 주관식 답은 단어 또는 짧은 구절이어야 합니다. 문장형 정답은 출제하지 마세요.
- 문제 순서는 반드시 1번·2번 객관식, 3번 주관식 순서를 지키세요.
- 모든 문제는 한국어로 작성하되, 기술 용어(라이브러리명, API명 등)는 원어 그대로 사용하세요.

## 예상 풀이 시간 (estimated_minutes)

각 레벨의 난이도에 맞게 예상 풀이 시간(분)을 정수로 입력하세요.
기준: beginner=10, junior=8, mid=6, senior=5 수준으로 조정하되, 글의 복잡도에 따라 ±2분 범위에서 조정하세요.

## 레벨별 출제 방향

**beginner**: 글에서 다루는 핵심 개념이 '무엇인지'를 검증하세요.
개념을 처음 접하는 독자가 글을 읽고 이해할 수 있는 수준의 문제를 출제하세요.
기술 용어 첫 등장 시 괄호 안에 짧은 설명을 추가하고, 비유나 예시를 활용하세요.

**junior**: 글에서 다루는 기술이 '어떻게 동작하는지', '왜 이 방식을 선택했는지'를 검증하세요.
개념을 알고 있지만 원리까지는 깊이 이해하지 못한 독자 수준의 문제를 출제하세요.
기본 기술 용어는 그대로 사용하되, 생소한 개념은 한 문장 이내로 짧게 부연하세요.

**mid**: 글에서 다루는 기술의 구현 세부사항, 주의사항, 성능 특성을 검증하세요.
실무에서 해당 기술을 직접 사용하는 개발자 수준의 문제를 출제하세요.
표준 기술 용어를 그대로 사용하고, 설명은 핵심만 간결하게 작성하세요.

**senior**: 글에서 다루는 기술의 설계 트레이드오프, 아키텍처 결정, 심화 엣지케이스를 검증하세요.
해당 기술을 깊이 이해하고 설계 결정을 내릴 수 있는 전문가 수준의 문제를 출제하세요.
전문 용어·약어를 자유롭게 사용하고, 설명에 트레이드오프나 심화 내용을 포함하세요.
"""

_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "estimated_minutes": {
            "type": "integer",
            "description": "이 레벨 퀴즈의 예상 풀이 시간(분). beginner=10, junior=8, mid=6, senior=5 수준",
        },
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
                                "id": {
                                    "type": "string",
                                    "description": "선지 ID (A~E)",
                                },
                                "text": {"type": "string", "description": "선지 내용"},
                            },
                            "required": ["id", "text"],
                        },
                        "description": "객관식 5개 선지 [{id, text}]. 주관식이면 빈 배열 []",
                    },
                    "correct_option_id": {
                        "type": "string",
                        "description": '정답 선지 ID (A~E). 주관식이면 빈 문자열 ""',
                    },
                    "explanation": {
                        "type": "string",
                        "description": "정답 이유 설명 (2~3문장)",
                    },
                    "correct_answer": {
                        "type": "string",
                        "description": "주관식: 자동 채점용 모범 답(단답). 객관식: 반드시 빈 문자열",
                    },
                },
                "required": [
                    "type",
                    "question",
                    "options",
                    "correct_option_id",
                    "explanation",
                    "correct_answer",
                ],
            },
        },
    },
    "required": ["estimated_minutes", "questions"],
}

QUIZ_TOOL = {
    "name": "save_quiz",
    "description": "퀴즈 제목과 4개 레벨(beginner·junior·mid·senior)별 퀴즈 3문제(객관식 2 + 주관식 1)를 저장합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "글의 핵심 주제를 담은 퀴즈 제목 (20자 이내, 한국어)",
            },
            "beginner": _QUESTIONS_SCHEMA,
            "junior": _QUESTIONS_SCHEMA,
            "mid": _QUESTIONS_SCHEMA,
            "senior": _QUESTIONS_SCHEMA,
        },
        "required": ["title", "beginner", "junior", "mid", "senior"],
    },
}


def build_retry_prompt(text: str, missing_levels: list[str]) -> str:
    """누락된 레벨만 재생성하는 사용자 프롬프트를 반환한다."""
    levels_str = "/".join(missing_levels)
    return (
        f"아래 기술 블로그 글을 읽고, {levels_str} 레벨에 해당하는 퀴즈 3문제(객관식 2 + 주관식 1)만 출제하세요.\n"
        f"1번·2번은 객관식 5지선다, 3번은 주관식 단답형으로 출제하세요.\n\n"
        f"---\n\n{text}"
    )


def build_retry_tool(missing_levels: list[str]) -> dict:
    """누락된 레벨만 required로 하는 retry용 tool 스키마를 반환한다."""
    return {
        "name": "save_quiz",
        "description": f"{', '.join(missing_levels)} 레벨 퀴즈 결과를 저장합니다.",
        "input_schema": {
            "type": "object",
            "properties": {level: _QUESTIONS_SCHEMA for level in missing_levels},
            "required": list(missing_levels),
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
        "아래 기술 블로그 글을 읽고, 퀴즈 제목과 핵심 내용을 검증하는 퀴즈 3문제를 "
        "4개 레벨(beginner·junior·mid·senior)로 출제하세요.\n"
        "1번·2번은 객관식 5지선다, 3번은 주관식 단답형으로 출제하세요.\n"
        "각 레벨은 레벨별 출제 방향에 따라 검증하는 지식의 깊이와 관점을 달리하세요.\n"
        "각 레벨의 난이도에 맞는 예상 풀이 시간도 함께 입력하세요.\n\n"
        "---\n\n"
        f"{text}"
    )
