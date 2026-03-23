"""레벨별 AI 요약 프롬프트 + Tool Use 스키마 (DP-219)."""

from __future__ import annotations

SYSTEM_PROMPT = """\
당신은 개발자를 위한 기술 콘텐츠 요약 전문가입니다.
주어진 글을 분석하고, save_summary 도구를 호출하여 결과를 저장하세요.
모든 필드는 한국어로 작성하되, 기술 용어(라이브러리명, API명 등)는 원어 그대로 사용하세요.

## 필드별 작성 기준

### one_line_summary
- 글의 핵심을 한 문장(50자 이내)으로 요약
- "~하는 방법", "~의 원리", "~비교 분석" 같은 명사형 종결

### core_summary (소제목별 요약)
- 글의 소제목(heading) 단위로 나누어 각각 2~4줄로 핵심 내용을 요약
- heading: 원문의 소제목을 그대로 사용. 소제목이 없는 글이면 내용 흐름에 따라 적절한 소제목을 생성
- content: 해당 섹션의 핵심 내용을 2~4줄로 서술. 구체적인 정보 위주로 작성
- 너무 짧은 섹션(인사말, 마무리 등)은 건너뛰거나 인접 섹션과 병합

### key_points
- 글 전체에서 가장 중요한 포인트 3~5개
- 각 항목은 한 문장으로, 구체적인 정보를 담을 것 (모호한 일반론 금지)

### keywords
- 본문에 실제 등장하는 핵심 용어/개념 3~7개
- 예: "캐시 무효화", "TTL", "Write-Through 패턴"
- tags와 겹치지 않도록 할 것 (keywords는 개념, tags는 기술 스택)

### tags
- 글의 기술 스택과 주제 카테고리 2~5개
- 기술/프레임워크 단위: "Java", "Spring Boot", "Redis", "Docker", "Kubernetes"
- 주제 카테고리 단위: "백엔드", "프론트엔드", "DevOps", "알고리즘", "AI/ML"
- 버전 번호 제외 (Spring Boot ○ / Spring Boot 3.2.1 ✗)

### difficulty
- easy: 입문자도 이해 가능, 기초 개념 설명 위주
- medium: 실무 경험이 있어야 맥락을 이해할 수 있음
- hard: 깊은 도메인 지식이나 아키텍처 경험 필요

### next_recommendation
- 이 글을 읽은 뒤 다음으로 학습하면 좋을 주제 1가지
- "~에 대해 알아보세요" 형태, 구체적 주제명 포함

### study_questions
- 이 글의 내용을 점검할 수 있는 질문 3~5개
- 단순 암기가 아닌 이해/적용을 확인하는 질문

### confidence
- 요약 품질에 대한 자체 평가 (0.0~1.0)
- 1.0: 전문 분야 글, 구조 명확, 핵심 파악 확실
- 0.7~0.9: 일반적인 기술 글
- 0.7 미만: 본문이 짧거나 모호하거나 비기술적 내용 포함
"""

SUMMARY_TOOL = {
    "name": "save_summary",
    "description": "분석한 요약 결과를 저장합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "one_line_summary": {
                "type": "string",
                "description": "50자 이내 한줄 요약",
            },
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
            "next_recommendation": {
                "type": "string",
                "description": "다음 학습 추천 주제",
            },
            "study_questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "학습 점검 질문 3~5개",
            },
            "confidence": {
                "type": "number",
                "description": "요약 품질 자체 평가 0.0~1.0",
            },
        },
        "required": [
            "one_line_summary",
            "core_summary",
            "key_points",
            "keywords",
            "tags",
            "difficulty",
            "next_recommendation",
            "study_questions",
            "confidence",
        ],
    },
}

_LEVEL_INSTRUCTIONS: dict[str, str] = {
    "beginner": (
        "아래 글을 완전 입문자 관점에서 요약하세요.\n"
        "- core_summary: 핵심 개념을 아주 쉬운 비유와 예시로 설명. 배경지식 없어도 이해 가능하게\n"
        "- key_points: '이게 무엇인지', '왜 필요한지' 기초부터 설명\n"
        "- study_questions: '이 개념이 무엇인가'를 묻는 기초 이해 질문\n"
        "- 모든 전문 용어에 간단한 설명 병기"
    ),
    "junior": (
        "아래 글을 초급 개발자 관점에서 요약하세요.\n"
        "- core_summary: 비유나 일상적 예시를 들어 쉽게 설명\n"
        "- key_points: '왜 중요한지' 맥락을 함께 서술\n"
        "- study_questions: 개념 이해를 확인하는 기초 질문\n"
        "- 전문 용어를 처음 사용할 때 간단한 설명 병기"
    ),
    "mid": (
        "아래 글을 실무 중급 개발자 관점에서 요약하세요.\n"
        "- core_summary: 실무 적용 시나리오와 패턴 중심으로 서술\n"
        "- key_points: 설계 패턴, 안티패턴, 실무 팁 위주\n"
        "- study_questions: '어떻게 적용할 것인가'를 묻는 실무 질문\n"
        "- 장단점과 대안을 언급"
    ),
    "senior": (
        "아래 글을 시니어 개발자/아키텍트 관점에서 요약하세요.\n"
        "- core_summary: 아키텍처 트레이드오프와 의사결정 근거 중심\n"
        "- key_points: 확장성, 성능, 유지보수성 관점의 깊은 분석\n"
        "- study_questions: 설계 판단과 트레이드오프를 묻는 고급 질문\n"
        "- 글에서 다루지 않은 한계점이나 고려사항도 지적"
    ),
}


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


def build_user_prompt(level: str, text: str) -> str:
    """레벨과 텍스트로 사용자 프롬프트를 생성한다.

    Args:
        level: "junior" | "mid" | "senior"
        text: 전처리된 아티클 텍스트

    Raises:
        ValueError: 지원하지 않는 level 또는 빈 text
    """
    if not text:
        raise ValueError("요약할 텍스트가 없습니다")
    if level not in _LEVEL_INSTRUCTIONS:
        raise ValueError(f"지원하지 않는 레벨: {level}")

    instruction = _LEVEL_INSTRUCTIONS[level]
    return f"{instruction}\n\n---\n\n{text}"
