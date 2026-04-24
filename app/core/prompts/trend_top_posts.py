"""Top 5 콘텐츠 주제 흐름 서사 요약 프롬프트 (DP-404)."""

from __future__ import annotations

from datetime import datetime

SYSTEM_PROMPT = """\
당신은 개발자 커뮤니티 동향 분석 전문가입니다.

이번 기간 가장 많이 조회된 글 정보를 바탕으로,
개발자들이 어떤 주제와 기술에 관심을 가졌는지 1~3 문단의 서사 요약을 작성합니다.

## 작성 원칙
- 특정 글을 "1위", "N번째 글" 등으로 직접 지칭하지 않습니다
- 조회수 숫자를 직접 언급하지 않습니다
- 광고성·추천성 표현을 사용하지 않습니다
- "프론트엔드 생태계 비교", "Spring + Kotlin 조합에 대한 관심" 같은 주제 군집 표현을 씁니다
- 200~400자 내외로 작성합니다
- 추천 액션은 출력하지 않습니다 (Insight/주간 리포트와 역할 분리)
- 이전 기간 요약이 제공된 경우, 마지막 문단에서 이전 기간과의 주제 변화를 자연스럽게 서술합니다
  - 예: "이번 주는 ~~한 흐름이 두드러지며, 지난 기간 ~~했던 것과 달리 ~~쪽으로 관심이 이동했습니다."
- 이전 기간 요약이 없으면 현재 기간만 서술합니다
"""

TOOL_SAVE_TOP_POSTS_SUMMARY = {
    "name": "save_top_posts_summary",
    "description": "Top 5 글의 주제 흐름 서사 요약을 저장한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "top_posts_summary": {
                "type": "string",
                "description": "Top 5 글의 주제 흐름 서사 요약 (200~400자, 1~3 문단)",
            }
        },
        "required": ["top_posts_summary"],
    },
}


def _format_daily_label(period_start: str, period_end: str) -> str:
    try:
        s = datetime.fromisoformat(period_start)
        e = datetime.fromisoformat(period_end)
        return f"{s.month}월 {s.day}일 {s.hour}시~{e.hour}시"
    except (ValueError, TypeError):
        return "오늘"


def build_user_prompt(
    top_contents: list[dict],
    summary_meta: dict[str, dict],
    period_start: str = "",
    period_end: str = "",
    unit: str = "weekly",
    prev_summary: str | None = None,
) -> str:
    if unit == "daily":
        period_label = _format_daily_label(period_start, period_end)
    elif unit == "weekly":
        period_label = "이번 주"
    elif unit == "monthly":
        period_label = "이번 달"
    else:
        period_label = "이번 기간"

    lines: list[str] = [f"기간: {period_label}", ""]
    lines.append("## 이번 기간 주목받은 글 (조회수 상위 5편)")
    lines.append("")

    for idx, content in enumerate(top_contents, 1):
        cid = content.get("id", "")
        meta = summary_meta.get(cid, {})
        title = content.get("translated_title") or content.get("title", "")
        category = content.get("category") or ""
        tags = content.get("tags") or []
        if isinstance(tags, str):
            import json

            try:
                tags = json.loads(tags)
            except (ValueError, TypeError):
                tags = []
        keywords = meta.get("keywords", [])
        one_line_summary = meta.get("one_line_summary", "")

        lines.append(f"[{idx}] 제목: {title}")
        if category:
            lines.append(f"    분류: {category}")
        if tags:
            lines.append(f"    태그: {', '.join(tags)}")
        if keywords:
            lines.append(f"    핵심 키워드: {', '.join(keywords)}")
        if one_line_summary:
            lines.append(f"    한줄 요약: {one_line_summary}")
        lines.append("")

    if prev_summary:
        lines.append("## 이전 기간 요약 (참고용)")
        lines.append(prev_summary)
        lines.append("")

    return "\n".join(lines).rstrip()
