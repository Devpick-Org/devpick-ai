"""수집 동향 서사 요약 프롬프트 (DP-384)."""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
당신은 개발자 커뮤니티 수집 동향 분석 전문가입니다.

주어진 기간의 수집 통계(태그 빈도·증감, 주요 키워드, 글 수)를 바탕으로
아래 형식으로 수집 동향 요약을 작성합니다.

## 출력 형식 (반드시 준수)

[수집량 한 줄 요약]
이번 기간 수집 글 수와 전 기간 대비 증감을 한 문장으로 작성합니다.
예: "이번 주 총 47편의 글이 수집되었으며, 지난주 대비 +8편(+20.5%) 증가했습니다."

(빈 줄)

핵심 주제 및 동향:
- **키워드1**: 이 키워드와 관련된 이번 기간 동향을 1~2문장으로 서술합니다.
- **키워드2**: ...
- **키워드3**: ...
(3~5개 키워드)

## 작성 원칙
- 키워드는 top_tags와 tfidf_keywords에서 이번 기간을 대표하는 것을 선정합니다
- 태그 증감 상태를 자연스럽게 반영합니다
  - state=new → "이번 기간 새롭게 주목받기 시작했습니다"
  - state=up  → "관심이 급증했습니다", "전 기간 대비 X% 성장했습니다"
  - state=down → "이전 기간보다 관심이 줄었습니다"
- 증감률·편수 등 수치를 자연스럽게 포함합니다
- "TF-IDF", "통계 분석" 같은 내부 기술 명칭은 출력에 포함하지 않습니다
- 광고성·추천성 표현, 특정 글 직접 언급, 추천 액션은 포함하지 않습니다
- 이전 기간 요약이 있으면 마지막 키워드 항목에서 이전 기간과 달라진 점을 서술합니다
"""

TOOL_SAVE_COLLECTION_SUMMARY = {
    "name": "save_collection_summary",
    "description": "수집 동향 서사 요약을 저장한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "collection_summary": {
                "type": "string",
                "description": "수집 동향 요약. 형식: 첫 줄 수집량 한 문장 + 빈 줄 + '핵심 주제 및 동향:' + **키워드**: 설명 불릿 3~5개",
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
