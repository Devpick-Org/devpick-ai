"""태그 빈도 집계 + 증감 상태 판정 (DP-380)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass
class TagFrequency:
    keyword: str
    cur_count: int
    prev_count: int
    delta: int
    growth_rate: float | None
    state: str


class FrequencyAnalyzer:
    """cur/prev 기간 태그 빈도를 집계하고 증감 상태를 판정한다."""

    def __init__(self, top_n: int | None = None, min_total: int = 3) -> None:
        self._top_n = top_n
        self._min_total = min_total

    def analyze(self, cur_tags: list[str], prev_tags: list[str]) -> list[TagFrequency]:
        """태그 빈도 집계 후 Top N TagFrequency 리스트를 반환한다.

        롱테일 필터:
            - cur + prev < min_total → 제외
            - prev=0 & cur < min_total → 제외 (cold start 노이즈)
        """
        cur_counter = Counter(cur_tags)
        prev_counter = Counter(prev_tags)
        all_tags = set(cur_counter) | set(prev_counter)

        results: list[TagFrequency] = []
        for tag in all_tags:
            cur = cur_counter.get(tag, 0)
            prev = prev_counter.get(tag, 0)

            if cur + prev < self._min_total:
                continue
            if prev == 0 and cur < self._min_total:
                continue

            state, delta, growth_rate = self._calc_state(cur, prev)
            results.append(
                TagFrequency(
                    keyword=tag,
                    cur_count=cur,
                    prev_count=prev,
                    delta=delta,
                    growth_rate=growth_rate,
                    state=state,
                )
            )

        results.sort(key=lambda x: x.cur_count, reverse=True)
        return results if self._top_n is None else results[: self._top_n]

    def _calc_state(self, cur: int, prev: int) -> tuple[str, int, float | None]:
        if prev == 0 and cur >= self._min_total:
            return "new", cur, None
        if prev > 0 and cur == 0:
            return "down", -prev, -100.0
        if cur > prev:
            rate = _clip((cur - prev) / prev * 100)
            return "up", cur - prev, rate
        if cur < prev and cur > 0:
            rate = _clip((cur - prev) / prev * 100)
            return "down", cur - prev, rate
        return "same", 0, 0.0


def _clip(value: float, lo: float = -300.0, hi: float = 300.0) -> float:
    return round(max(lo, min(hi, value)), 2)
