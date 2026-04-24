"""수집 동향 서사 요약 프롬프트 (DP-384)."""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
당신은 개발자 커뮤니티 수집 동향 분석 전문가입니다.

주어진 기간의 수집 통계(태그 빈도·증감, 주요 키워드, 글 수)를 바탕으로
개발자 커뮤니티가 어떤 주제를 다루고 있는지 1~3 문단의 서사 요약을 작성합니다.

## 작성 원칙
- 수집 글 수, 태그 빈도, 증감률 등 수치를 자연스럽게 인용해 전문성을 높입니다
  - 예: "47편의 글 수집", "전주 대비 +23.7%", "Kubernetes(+50%)"
- 태그 증감/신규를 흐름으로 연결합니다
  - state=new → "이번 기간 새롭게 등장"
  - state=up  → "관심 급증", "전 기간 대비 X% 성장"
  - state=down → "관심 감소"
- 핵심 키워드는 "이번 기간 수집 글 전반에서 자주 등장한 표현"으로 자연스럽게 서술합니다
  - "TF-IDF", "통계 분석" 같은 기술 명칭은 출력에 포함하지 않습니다
  - 예: "이번 주 수집 글에서 자주 언급된 키워드로는 ..."
  - 키워드를 흐름 서술에 녹여 씁니다 — 단순 나열 금지
- 광고성·추천성 표현을 사용하지 않습니다
- 특정 글을 직접 언급하지 않습니다
- 200~400자 내외로 작성합니다
- 추천 액션은 출력하지 않습니다 (Insight/주간 리포트와 역할 분리)
- 이전 기간 요약이 제공된 경우, 마지막 문단에서 이전 기간과의 차이점을 자연스럽게 서술합니다
- 이전 기간 요약이 없으면 현재 기간 서술만 합니다
"""

TOOL_SAVE_COLLECTION_SUMMARY = {
    "name": "save_collection_summary",
    "description": "수집 동향 서사 요약을 저장한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "collection_summary": {
                "type": "string",
                "description": "수집 동향 서사 요약 (200~400자, 1~3 문단, 수치 포함)",
            }
        },
        "required": ["collection_summary"],
    },
}


def build_user_prompt(signals: Any) -> str:
    """TrendSignals → LLM 사용자 프롬프트 문자열 변환."""
    unit = signals.unit
    if unit == "weekly":
        period_label = "이번 주"
    elif unit == "monthly":
        period_label = "이번 달"
    else:
        period_label = "이번 기간"

    lines: list[str] = [
        f"기간: {period_label} ({signals.period_start} ~ {signals.period_end})",
        "",
        "## 수집 현황",
        f"- 이번 기간: {signals.cur_content_count}편",
        f"- 이전 기간: {signals.prev_content_count}편",
    ]

    if signals.prev_content_count > 0:
        delta = signals.cur_content_count - signals.prev_content_count
        rate = delta / signals.prev_content_count * 100
        lines.append(f"- 증감: {delta:+d}편 ({rate:+.1f}%)")
    lines.append("")

    if signals.top_tags:
        lines.append("## Top 10 태그 (이번 기간 빈도 순)")
        lines.append("태그 | 이번 | 이전 | 증감 | 상태")
        for tf in signals.top_tags:
            delta_str = f"{tf.delta:+d}" if tf.delta != 0 else "0"
            lines.append(
                f"{tf.keyword} | {tf.cur_count} | {tf.prev_count}"
                f" | {delta_str} | {tf.state}"
            )
        lines.append("")

        new_tags = [tf.keyword for tf in signals.top_tags if tf.state == "new"]
        if new_tags:
            lines.append("## 신규 등장 태그")
            lines.append(", ".join(new_tags))
            lines.append("")

        up_tags = sorted(
            [tf for tf in signals.top_tags if tf.state == "up"],
            key=lambda x: x.delta,
            reverse=True,
        )[:5]
        if up_tags:
            lines.append("## 급증 태그 Top 5 (state=up, delta 상위)")
            for tf in up_tags:
                rate_str = (
                    f"+{tf.growth_rate:.1f}%" if tf.growth_rate is not None else "신규"
                )
                lines.append(f"- {tf.keyword}: +{tf.delta}건 ({rate_str})")
            lines.append("")

    if signals.tfidf_keywords:
        lines.append("## 이번 기간 주요 키워드 (수집 글 전반 빈도 기반, 상위 15)")
        lines.append(", ".join(signals.tfidf_keywords[:15]))
        lines.append("")

    if signals.prev_summary:
        lines.append("## 이전 기간 collection_summary (참고용)")
        lines.append(signals.prev_summary)
        lines.append("")

    return "\n".join(lines).rstrip()
