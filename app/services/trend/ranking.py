"""트렌드 랭킹 — Top 5 조회 콘텐츠 + Top 10 태그 선정 (DP-383)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.services.trend.frequency import TagFrequency


@dataclass
class RankedTag:
    keyword: str
    cur_count: int
    prev_count: int
    delta: int
    growth_rate: float | None
    state: str
    tag_count: int
    score: float
    rank_change: int = 0


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class TrendRanker:
    """기간 조회수 기반 Top 5 콘텐츠와 복합 점수 기반 Top 10 태그를 선정한다."""

    def __init__(self, top_contents: int = 5, top_tags: int = 10) -> None:
        self._top_contents = top_contents
        self._top_tags = top_tags

    def rank_contents(
        self,
        cur_view_counts: dict[str, int],
        content_details: list[dict],
    ) -> list[dict]:
        """기간 조회수 내림차순 Top N 콘텐츠를 반환한다.

        content_details: ContentRepository.find_by_ids() 결과
        반환 dict에 view_count 필드 추가.
        """
        if not cur_view_counts or not content_details:
            return []
        details_map = {str(c["id"]): c for c in content_details}
        filtered = {
            cid: count
            for cid, count in cur_view_counts.items()
            if cid in details_map
        }
        top_ids = sorted(filtered, key=filtered.__getitem__, reverse=True)[
            : self._top_contents
        ]
        result = []
        for rank, cid in enumerate(top_ids, start=1):
            item = dict(details_map[cid])
            item["view_count"] = filtered[cid]
            item["rank"] = rank
            result.append(item)
        return result

    def rank_tags(
        self,
        tag_frequencies: list[TagFrequency],
        summary_meta: dict[str, dict],
        external_signals: dict[str, float] | None = None,
        top_n: int | None = None,
    ) -> list[RankedTag]:
        """태그 복합 점수 계산 후 Top N 을 반환한다.

        내부 태그: delta/growth_rate/category_match 기반 점수 + 외부 시그널 보정
        외부 전용 태그: 내부 데이터가 없어도 외부 시그널 점수만으로 후보 등록
        """
        categories = {
            meta["category"] for meta in summary_meta.values() if meta.get("category")
        }
        external = external_signals or {}
        ranked: list[RankedTag] = []
        internal_keywords: set[str] = set()

        for tf in tag_frequencies:
            internal_keywords.add(tf.keyword)
            category_match = tf.keyword in categories
            tag_count = tf.cur_count + (2 if category_match else 0)
            gr = tf.growth_rate if tf.growth_rate is not None else 0.0
            delta_score = math.log1p(abs(tf.delta)) * (1 if tf.delta >= 0 else -1) * 2.5
            score = (
                delta_score
                + 0.5 * _clip(gr, -5.0, 5.0)
                + (2.0 if category_match else 0.0)
                + (1.5 if tf.state == "new" else 0.0)
                + external.get(tf.keyword, 0.0)
            )
            ranked.append(
                RankedTag(
                    keyword=tf.keyword,
                    cur_count=tf.cur_count,
                    prev_count=tf.prev_count,
                    delta=tf.delta,
                    growth_rate=tf.growth_rate,
                    state=tf.state,
                    tag_count=tag_count,
                    score=round(score, 4),
                )
            )

        for kw, ext_score in external.items():
            if kw in internal_keywords:
                continue
            ranked.append(
                RankedTag(
                    keyword=kw,
                    cur_count=0,
                    prev_count=0,
                    delta=0,
                    growth_rate=None,
                    state="new",
                    tag_count=0,
                    score=round(ext_score, 4),
                )
            )

        ranked.sort(key=lambda x: x.score, reverse=True)
        limit = top_n if top_n is not None else self._top_tags
        return ranked[:limit]
