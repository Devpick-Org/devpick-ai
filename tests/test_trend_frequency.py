"""FrequencyAnalyzer 단위 테스트 (DP-380)."""

from __future__ import annotations

from app.services.trend.frequency import FrequencyAnalyzer


def _analyzer() -> FrequencyAnalyzer:
    return FrequencyAnalyzer(top_n=10, min_total=3)


# ── 상태 판정 ─────────────────────────────────────────────────────────────────


def test_state_new() -> None:
    result = _analyzer().analyze(["python"] * 3, [])
    assert len(result) == 1
    assert result[0].state == "new"
    assert result[0].delta == 3
    assert result[0].growth_rate is None


def test_state_up() -> None:
    result = _analyzer().analyze(["python"] * 6, ["python"] * 3)
    assert result[0].state == "up"
    assert result[0].delta == 3
    assert result[0].growth_rate == 100.0


def test_state_down_to_zero() -> None:
    result = _analyzer().analyze([], ["python"] * 3)
    assert result[0].state == "down"
    assert result[0].delta == -3
    assert result[0].growth_rate == -100.0


def test_state_down() -> None:
    result = _analyzer().analyze(["python"] * 2, ["python"] * 4)
    assert result[0].state == "down"
    assert result[0].delta == -2
    assert result[0].growth_rate == -50.0


def test_state_same() -> None:
    result = _analyzer().analyze(["python"] * 3, ["python"] * 3)
    assert result[0].state == "same"
    assert result[0].delta == 0
    assert result[0].growth_rate == 0.0


# ── 롱테일 필터 ───────────────────────────────────────────────────────────────


def test_longtail_filter_excludes_low_total() -> None:
    # cur+prev = 2 < 3 → 제외
    result = _analyzer().analyze(["python"] * 1, ["python"] * 1)
    assert result == []


def test_cold_start_filter_excludes_low_new() -> None:
    # prev=0 & cur=2 < 3 → 제외
    result = _analyzer().analyze(["python"] * 2, [])
    assert result == []


# ── Top N ─────────────────────────────────────────────────────────────────────


def test_top_n_limit() -> None:
    tags = [f"tag{i}" for i in range(15) for _ in range(3)]
    result = FrequencyAnalyzer(top_n=10, min_total=3).analyze(tags, [])
    assert len(result) == 10


def test_top_n_none_returns_all_candidates() -> None:
    """top_n=None(기본값)일 때 cut 없이 모든 후보를 반환해야 한다."""
    tags = [f"tag{i}" for i in range(15) for _ in range(3)]
    result = FrequencyAnalyzer(min_total=3).analyze(tags, [])
    assert len(result) == 15
