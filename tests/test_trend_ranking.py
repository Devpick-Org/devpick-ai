"""TrendRanker 단위 테스트 (DP-383)."""

from __future__ import annotations

import math

from app.services.trend.frequency import TagFrequency
from app.services.trend.ranking import TrendRanker


def _ranker() -> TrendRanker:
    return TrendRanker(top_contents=5, top_tags=10)


def _tf(
    keyword: str,
    cur: int = 3,
    prev: int = 3,
    delta: int = 0,
    growth_rate: float | None = 0.0,
    state: str = "same",
) -> TagFrequency:
    return TagFrequency(
        keyword=keyword,
        cur_count=cur,
        prev_count=prev,
        delta=delta,
        growth_rate=growth_rate,
        state=state,
    )


def _details(ids: list[str]) -> list[dict]:
    return [
        {
            "id": cid,
            "title": f"글 {cid}",
            "translated_title": None,
            "category": None,
            "tags": "[]",
            "source_id": "src-1",
            "published_at": None,
        }
        for cid in ids
    ]


# ── Top 5 콘텐츠 ──────────────────────────────────────────────────────────────


def test_rank_contents_sorted_by_view_count() -> None:
    view_counts = {"cid-1": 10, "cid-2": 50, "cid-3": 5}
    details = _details(["cid-1", "cid-2", "cid-3"])
    result = _ranker().rank_contents(view_counts, details)
    assert [r["id"] for r in result] == ["cid-2", "cid-1", "cid-3"]


def test_rank_contents_rank_field_is_1_based() -> None:
    view_counts = {"cid-1": 10, "cid-2": 50, "cid-3": 5}
    details = _details(["cid-1", "cid-2", "cid-3"])
    result = _ranker().rank_contents(view_counts, details)
    assert result[0]["rank"] == 1
    assert result[1]["rank"] == 2
    assert result[2]["rank"] == 3


def test_rank_contents_rank_contiguous_when_id_missing() -> None:
    view_counts = {"cid-1": 10, "cid-2": 50, "cid-3": 5}
    details = _details(["cid-1", "cid-3"])  # cid-2 details 없음
    result = _ranker().rank_contents(view_counts, details)
    ranks = [r["rank"] for r in result]
    assert ranks == list(range(1, len(result) + 1))


def test_rank_contents_view_count_zero_included() -> None:
    view_counts = {"cid-1": 0}
    details = _details(["cid-1"])
    result = _ranker().rank_contents(view_counts, details)
    assert len(result) == 1
    assert result[0]["view_count"] == 0


def test_rank_contents_adds_view_count_field() -> None:
    view_counts = {"cid-1": 7}
    details = _details(["cid-1"])
    result = _ranker().rank_contents(view_counts, details)
    assert result[0]["view_count"] == 7


# ── Top 10 태그 ───────────────────────────────────────────────────────────────


def test_rank_tags_new_bonus() -> None:
    tf_new = _tf("rust", cur=3, prev=0, delta=3, growth_rate=None, state="new")
    tf_same = _tf("python", cur=3, prev=3, delta=0, growth_rate=0.0, state="same")
    result = _ranker().rank_tags([tf_new, tf_same], {})
    new_tag = next(r for r in result if r.keyword == "rust")
    same_tag = next(r for r in result if r.keyword == "python")
    assert new_tag.score > same_tag.score
    # log1p(3)*2.5 + new_bonus(1.5)
    assert new_tag.score == round(math.log1p(3) * 2.5 + 1.5, 4)


def test_rank_tags_category_match_bonus() -> None:
    tf = _tf("backend", cur=5, prev=3, delta=2, growth_rate=2.0, state="up")
    summary_meta = {"cid-1": {"tags": ["backend"], "category": "backend"}}
    result = _ranker().rank_tags([tf], summary_meta)
    assert result[0].tag_count == 7  # 5 + 2
    # log1p(2)*2.5 + 0.5*growth(2.0) + category_bonus(2.0)
    assert result[0].score == round(math.log1p(2) * 2.5 + 0.5 * 2.0 + 2.0, 4)


def test_rank_tags_growth_rate_none_safe() -> None:
    tf = _tf("new-tech", cur=4, prev=0, delta=4, growth_rate=None, state="new")
    result = _ranker().rank_tags([tf], {})
    assert len(result) == 1
    assert isinstance(result[0].score, float)
    import math

    assert not math.isnan(result[0].score)


def test_rank_tags_sorted_by_score() -> None:
    tags = [
        _tf("a", cur=2, prev=1, delta=1, growth_rate=1.0, state="up"),
        _tf("b", cur=5, prev=3, delta=2, growth_rate=2.0, state="up"),
        _tf("c", cur=3, prev=3, delta=0, growth_rate=0.0, state="same"),
    ]
    result = _ranker().rank_tags(tags, {})
    scores = [r.score for r in result]
    assert scores == sorted(scores, reverse=True)


# ── external_signals ──────────────────────────────────────────────────────────


def test_rank_tags_external_signals_boost_score() -> None:
    tf_boosted = _tf("rust", cur=2, prev=1, delta=1, growth_rate=1.0, state="up")
    tf_plain = _tf("java", cur=2, prev=1, delta=1, growth_rate=1.0, state="up")
    result = _ranker().rank_tags(
        [tf_boosted, tf_plain], {}, external_signals={"rust": 0.9}
    )
    rust = next(r for r in result if r.keyword == "rust")
    java = next(r for r in result if r.keyword == "java")
    assert rust.score > java.score
    assert rust.score == round(java.score + 0.9, 4)


def test_rank_tags_external_signals_none_same_as_empty() -> None:
    tf = _tf("python", cur=3, prev=2, delta=1, growth_rate=1.0, state="up")
    result_none = _ranker().rank_tags([tf], {}, external_signals=None)
    result_empty = _ranker().rank_tags([tf], {}, external_signals={})
    assert result_none[0].score == result_empty[0].score


def test_rank_tags_external_signals_unknown_tag_ignored() -> None:
    tf = _tf("python", cur=3, prev=2, delta=1, growth_rate=1.0, state="up")
    result = _ranker().rank_tags([tf], {}, external_signals={"rust": 0.9})
    # rust 시그널이 있어도 python에는 영향 없음
    expected = round(math.log1p(1) * 2.5 + 0.5 * 1.0, 4)
    assert result[0].score == expected


def test_rank_tags_rank_change_default_zero() -> None:
    tf = _tf("python", cur=3, prev=2, delta=1, growth_rate=1.0, state="up")
    result = _ranker().rank_tags([tf], {})
    assert result[0].rank_change == 0


# ── 새 score 공식 검증 ─────────────────────────────────────────────────────────


def test_score_log_scale_flattens_large_delta() -> None:
    """log scale 적용 시 delta=50이 delta=5보다 점수가 높지만 선형보다 격차가 작아야 한다."""
    tf_small = _tf("a", cur=10, prev=5, delta=5, growth_rate=100.0, state="up")
    tf_large = _tf("b", cur=55, prev=5, delta=50, growth_rate=1000.0, state="up")
    result = _ranker().rank_tags([tf_small, tf_large], {})
    score_small = next(r.score for r in result if r.keyword == "a")
    score_large = next(r.score for r in result if r.keyword == "b")
    assert score_large > score_small
    # 선형이라면 large/small = 10배, log scale이면 훨씬 작음
    assert score_large / score_small < 5


def test_new_state_bonus_competes_with_popular_tag() -> None:
    """state='new' 소규모 태그가 state='up' 인기 태그와 경쟁 가능해야 한다."""
    tf_popular = _tf("react", cur=50, prev=45, delta=5, growth_rate=11.0, state="up")
    tf_new = _tf("bun", cur=8, prev=0, delta=8, growth_rate=None, state="new")
    result = _ranker().rank_tags([tf_popular, tf_new], {})
    react = next(r for r in result if r.keyword == "react")
    bun = next(r for r in result if r.keyword == "bun")
    # bun이 react보다 높거나, 점수 차이가 react의 30% 이내여야 한다
    assert bun.score > react.score * 0.7


def test_growth_clip_extended_to_5() -> None:
    """growth_rate=4.0이 기존 ±3 clip에선 3.0으로 잘렸지만 새 ±5 clip에선 4.0으로 통과해야 한다."""
    tf_4pct = _tf("htmx", cur=5, prev=1, delta=4, growth_rate=4.0, state="up")
    tf_3pct = _tf("htmx_old", cur=5, prev=1, delta=4, growth_rate=3.0, state="up")
    result_4 = _ranker().rank_tags([tf_4pct], {})
    result_3 = _ranker().rank_tags([tf_3pct], {})
    # 새 clip ±5 하에서 4.0은 3.0보다 score가 높아야 한다
    assert result_4[0].score > result_3[0].score
