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
- category: 글의 대분류. 반드시 다음 중 하나 선택:
  Frontend, Backend, Mobile, DevOps, Database, AI/ML, Security, Architecture, Language, CS Fundamentals
- tags: 기술 스택 태그 2~5개. 반드시 user message에서 제공된 허용 태그 목록에서만 선택하세요. 목록에 없는 태그는 절대 사용 금지.
  버전 번호 제외. tags와 keywords가 겹치지 않게 (tags=기술 스택, keywords=개념)
- difficulty: easy(입문자도 이해 가능) / medium(실무 경험 필요) / hard(깊은 도메인 지식 필요)
  - 원문의 **실제 난이도**만 반영한다. 습관적으로 medium을 고르지 말 것. 튜토리얼·소개 글이면 easy, 일반 실무 깊이면 medium, 도메인·아키텍처·성능이 깊게 얽히면 hard.

### beginner / junior / mid / senior (레벨별 필드)
각 레벨은 독립적인 독자를 대상으로 작성하세요:

- beginner: 완전 입문자. "이게 뭔가요? 왜 이 문제가 생겼나요? 어떻게 됐나요?" 스토리 중심. 기술 용어 첫 등장 시 괄호로 짧게 설명 (예: "트랜잭션(작업 묶음)"). 배경→문제→해결 흐름 유지
- junior: 초급 개발자. "어떻게 접근했나요? 왜 이 방법을 선택했나요?" 과정과 판단 근거 중심. 비유/예시 활용. 실패한 시도가 있으면 왜 실패했는지 반드시 포함
- mid: 중급 실무자. "이 패턴/구조의 실무적 의미는? 성능·비용 수치는? 다른 선택지와 비교하면?" 구체적 수치·패턴명·도입 시 고려사항 중심. 표준 기술 용어 사용
- senior: 시니어/아키텍트. "왜 이 설계를 선택했나? 무엇을 포기했나? 이 접근이 틀리는 경우는?" 아키텍처 결정의 근거·전제조건·대안 트레이드오프 중심. 전문 용어·약어 사용

각 레벨 공통 필드:
- core_summary: 반드시 문자열(string)로 출력. 형식: {소제목}\n{내용}\n\n{소제목}\n{내용}
  - 섹션 수: 원본 글 소제목 구조를 따라 3~4개. 유사한 소제목은 합쳐서 4개를 넘지 말 것
  - 소제목: 원본 소제목 우선 사용. 없을 경우에만 논지가 드러나는 제목 생성 ("프로젝트 배경" 같은 분류어 금지)
  - 내용: 해당 섹션의 핵심 포인트를 2~3문장으로 작성. 수치·명칭·구체적 사실 포함. "~노력했습니다" 같이 내용 없는 결론 동사만 쓰는 문장 금지
  - 마크다운 기호(#, -, *) 없이 plain text로 작성. 원문에 없는 사실·수치·고유명사 생성 금지
- key_points: 해당 레벨 독자에게 중요한 포인트 정확히 3개
- additional_questions: 해당 레벨에 맞는 이해/적용 점검 질문 정확히 3개
- next_recommendation: 이 글 다음에 학습할 주제 1가지. "~에 대해 알아보세요" 형태
- confidence: 요약 품질 자체 평가 0.0~1.0 (1.0=전문 분야/구조 명확, 0.7=일반 기술 글, 0.7 미만=짧거나 모호)
  - **레벨마다 요약의 충실도·명확성이 다르므로 beginner/junior/mid/senior의 confidence는 서로 다른 값이어야 한다.** 네 레벨 모두 같은 숫자(예: 0.9)로 맞추지 말 것. 0.55~0.98 범위에서 레벨별로 구체적으로 다르게 제시한다.
"""

_LEVEL_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "core_summary": {
            "type": "string",
            "description": "소제목+내용을 줄바꿈으로 연결한 문자열. 형식: heading\\ncontent\\n\\nheading\\ncontent",
        },
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "핵심 포인트 3개",
        },
        "additional_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "학습 점검 질문 3개",
        },
        "next_recommendation": {
            "type": "string",
            "description": "다음 학습 추천 주제",
        },
        "confidence": {
            "type": "number",
            "description": (
                "이 레벨 요약의 품질 자체 평가 0.0~1.0. "
                "beginner/junior/mid/senior 네 값은 서로 달라야 하며 동일 값(예: 모두 0.9) 금지."
            ),
        },
    },
    "required": [
        "core_summary",
        "key_points",
        "additional_questions",
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
                    "category": {
                        "type": "string",
                        "enum": [
                            "Frontend",
                            "Backend",
                            "Mobile",
                            "DevOps",
                            "Database",
                            "AI/ML",
                            "Security",
                            "Architecture",
                            "Language",
                            "CS Fundamentals",
                        ],
                        "description": "글의 기술 대분류",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "기술 스택 태그 2~5개 (우선 목록 참고, 새 기술은 자유 추가)",
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                        "description": (
                            "원문 이해에 필요한 난이도. 습관적으로 medium만 쓰지 말고 글에 맞게 선택."
                        ),
                    },
                },
                "required": [
                    "one_line_summary",
                    "keywords",
                    "category",
                    "tags",
                    "difficulty",
                ],
            },
            "beginner": _LEVEL_SUMMARY_SCHEMA,
            "junior": _LEVEL_SUMMARY_SCHEMA,
            "mid": _LEVEL_SUMMARY_SCHEMA,
            "senior": _LEVEL_SUMMARY_SCHEMA,
        },
        "required": ["common", "beginner", "junior", "mid", "senior"],
    },
}


def build_retry_prompt(text: str, missing_levels: list[str]) -> str:
    """누락된 레벨만 재생성하는 사용자 프롬프트를 반환한다."""
    levels_str = "/".join(missing_levels)
    return (
        f"아래 기술 글에서 {levels_str} 레벨 요약만 생성하세요.\n"
        f"core_summary는 반드시 문자열 형식(heading\\ncontent\\n\\nheading\\ncontent)으로 작성하세요.\n\n"
        f"---\n\n{text}"
    )


def build_retry_tool(missing_levels: list[str]) -> dict:
    """누락된 레벨만 required로 하는 retry용 tool 스키마를 반환한다."""
    return {
        "name": "save_all_summaries",
        "description": f"{', '.join(missing_levels)} 레벨 요약 결과를 저장합니다.",
        "input_schema": {
            "type": "object",
            "properties": {level: _LEVEL_SUMMARY_SCHEMA for level in missing_levels},
            "required": list(missing_levels),
        },
    }


def build_user_prompt_all_levels(
    text: str, allowed_tags: list[str] | None = None
) -> str:
    """4레벨 동시 생성용 사용자 프롬프트를 생성한다.

    Args:
        text: 전처리된 아티클 텍스트
        allowed_tags: tags 필드에 사용 가능한 태그 이름 목록 (None이면 제약 없음)

    Raises:
        ValueError: 빈 text
    """
    if not text:
        raise ValueError("요약할 텍스트가 없습니다")
    tag_constraint = ""
    if allowed_tags:
        tag_list = ", ".join(allowed_tags)
        tag_constraint = (
            f"\n허용 태그 목록 (common.tags는 반드시 이 목록에서만 선택, 목록 외 태그 사용 금지):\n{tag_list}\n"
        )
    return (
        f"아래 기술 글을 beginner/junior/mid/senior 4개 레벨로 동시에 요약하세요.\n"
        f"core_summary는 반드시 문자열 형식(heading\\ncontent\\n\\nheading\\ncontent)으로 작성하세요.\n"
        f"common.difficulty는 원문 난이도에 맞게 easy/medium/hard 중 하나만 선택(대부분을 medium으로 두지 말 것). "
        f"레벨별 confidence는 네 값이 서로 달라야 합니다.{tag_constraint}\n\n"
        f"---\n\n{text}"
    )
