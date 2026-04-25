"""트렌드 랭킹 — Top 5 조회 콘텐츠 + Top 10 태그 선정 (DP-383)."""

from __future__ import annotations

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
        details_map = {c["id"]: c for c in content_details}
        top_ids = sorted(
            cur_view_counts, key=cur_view_counts.__getitem__, reverse=True
        )[: self._top_contents]
        result = []
        rank = 1
        for cid in top_ids:
            if cid in details_map:
                item = dict(details_map[cid])
                item["view_count"] = cur_view_counts[cid]
                item["rank"] = rank
                result.append(item)
                rank += 1
        return result

    def rank_tags(
        self,
        tag_frequencies: list[TagFrequency],
        summary_meta: dict[str, dict],
        external_signals: dict[str, float] | None = None,
    ) -> list[RankedTag]:
        """태그 복합 점수 계산 후 Top N 을 반환한다.

        score = 0.5 × delta
              + 0.5 × clip(growth_rate, -3.0, 3.0)
              + (2.0 if category_match else 0.0)   # α=2
              + (0.5 if state="new" else 0.0)       # new_bonus
        growth_rate=None(state="new") → 0.0 처리
        """
        categories = {
            meta["category"] for meta in summary_meta.values() if meta.get("category")
        }
        external = external_signals or {}
        ranked: list[RankedTag] = []
        for tf in tag_frequencies:
            category_match = tf.keyword in categories
            tag_count = tf.cur_count + (2 if category_match else 0)
            gr = tf.growth_rate if tf.growth_rate is not None else 0.0
            score = (
                0.5 * tf.delta
                + 0.5 * _clip(gr, -3.0, 3.0)
                + (2.0 if category_match else 0.0)
                + (0.5 if tf.state == "new" else 0.0)
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
        ranked.sort(key=lambda x: x.score, reverse=True)
        return ranked[: self._top_tags]
