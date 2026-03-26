"""주간 인사이트 생성 프롬프트 + Tool Use 스키마 (DP-260)."""

from __future__ import annotations

from app.schemas.insight import ActivityData

SYSTEM_PROMPT = """\
당신은 개발자 성장 플랫폼 DevPick의 주간 학습 인사이트 분석가입니다.
유저의 이번 주 학습 활동 데이터를 분석하고, save_insight 도구를 호출하여 결과를 저장하세요.
모든 내용은 한국어로 작성하되, 기술 용어(라이브러리명, API명, 프레임워크명 등)는 원어 그대로 사용하세요.

## 작성 원칙

### well_done (잘한 점)
- "이번 주에 ~" 로 시작하세요
- 구체적인 숫자와 기술명을 활용하세요 (예: "Redis와 Spring Boot 관련 글 5편을 읽고")
- 스크랩한 글은 유저가 특히 중요하다고 판단한 것이므로 강조하세요
- 작성한 질문이 있다면 실무적인 고민을 언급하세요
- 활동이 적어도 있는 것을 찾아 진심으로 칭찬하세요

### lacking (아쉬운 점)
- "다만 ~" 또는 "한편 ~" 으로 시작하세요
- 비난이 아닌 건설적 피드백으로 작성하세요
- 데이터에 근거해서 개선 가능한 포인트를 제시하세요
- 예: 특정 요일 활동 없음, 특정 분야 편중, 질문 활용 부족 등

### next_week (다음 주 추천)
- "다음 주에는 ~" 로 시작하세요
- 이번 주 활동을 자연스럽게 이어가는 방향을 제안하세요
- 실천 가능한 구체적 목표 1~2개를 제시하세요
- 스크랩한 글이나 작성한 질문의 주제와 연결해서 제안하세요

## 공통 규칙
- 각 필드는 2~4문장으로 간결하게 작성하세요
- 활동이 전혀 없는 경우에도 격려하며 작은 목표를 제안하세요
- 스크랩한 글 > 읽은 글 순으로 가중치를 두어 분석하세요
"""

INSIGHT_TOOL = {
    "name": "save_insight",
    "description": "주간 학습 인사이트를 저장합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "well_done": {
                "type": "string",
                "description": "이번 주 잘한 점 (2~4문장, '이번 주에 ~' 시작)",
            },
            "lacking": {
                "type": "string",
                "description": "아쉬운 점 / 개선 포인트 (2~4문장, '다만 ~' 또는 '한편 ~' 시작)",
            },
            "next_week": {
                "type": "string",
                "description": "다음 주 추천 방향 (2~4문장, '다음 주에는 ~' 시작)",
            },
        },
        "required": ["well_done", "lacking", "next_week"],
    },
}


def build_user_prompt(
    activities: ActivityData,
    ai_events: dict,
    read_summaries: list[dict],
    scrapped_summaries: list[dict],
    question_texts: list[str],
    week_start: str,
    week_end: str,
) -> str:
    """주간 인사이트 생성용 사용자 프롬프트를 생성한다.

    Args:
        activities: 백엔드가 전달한 주간 활동 집계.
        ai_events: AI 기능 활용 카운트 {"refine": int, "answer": int, "similar": int}.
        read_summaries: 읽은 글 one_line_summary 목록.
        scrapped_summaries: 스크랩한 글 one_line_summary 목록.
        question_texts: 작성한 질문 텍스트 목록.
        week_start: 기간 시작 (ISO date 문자열, 예: "2026-03-17").
        week_end: 기간 종료 (ISO date 문자열, 예: "2026-03-23").

    Returns:
        Claude에게 전달할 사용자 프롬프트.
    """
    parts: list[str] = [f"기간: {week_start} ~ {week_end}"]

    # 기본 활동 요약
    parts.append(
        "## 기본 활동\n"
        f"- 콘텐츠 읽기: {activities.contents_read}개"
        f" / 질문 작성: {activities.questions_created}개"
        f" / 스크랩: {activities.scraps_count}개"
    )

    # 읽은 글 (one_line_summary)
    if read_summaries:
        lines = "\n".join(f"- {s['one_line_summary']}" for s in read_summaries)
        parts.append(f"## 이번 주 읽은 글\n{lines}")
    else:
        parts.append("## 이번 주 읽은 글\n- 없음")

    # 스크랩한 글 (가중치 높음)
    if scrapped_summaries:
        lines = "\n".join(f"- {s['one_line_summary']}" for s in scrapped_summaries)
        parts.append(f"## 이번 주 스크랩한 글 (유저가 중요하다고 판단한 글)\n{lines}")
    else:
        parts.append("## 이번 주 스크랩한 글 (유저가 중요하다고 판단한 글)\n- 없음")

    # 작성한 질문
    if question_texts:
        lines = "\n".join(f"- {t}" for t in question_texts)
        parts.append(f"## 이번 주 작성한 질문\n{lines}")
    else:
        parts.append("## 이번 주 작성한 질문\n- 없음")

    # 요일별 활동 패턴
    if activities.daily_activities:
        day_strs = " | ".join(
            f"{d.day_of_week}: {d.count}" for d in activities.daily_activities
        )
        parts.append(f"## 요일별 활동 패턴\n{day_strs}")

    # 관심 기술 태그
    if activities.tag_activities:
        tag_strs = " | ".join(
            f"{t.tag_name}: {t.count}" for t in activities.tag_activities
        )
        parts.append(f"## 관심 기술 태그\n{tag_strs}")
    elif activities.top_tags:
        tag_strs = " | ".join(f"{t.tag}: {t.count}" for t in activities.top_tags)
        parts.append(f"## 관심 기술 태그 (상위)\n{tag_strs}")

    # AI 기능 활용 현황
    refine_cnt = ai_events.get("refine", 0)
    answer_cnt = ai_events.get("answer", 0)
    similar_cnt = ai_events.get("similar", 0)
    parts.append(
        "## AI 기능 활용\n"
        f"- 질문 개선: {refine_cnt}회"
        f" / AI 답변: {answer_cnt}회"
        f" / 유사 질문 검색: {similar_cnt}회"
    )

    return "\n\n".join(parts)
