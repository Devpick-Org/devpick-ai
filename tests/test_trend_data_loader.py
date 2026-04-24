"""TrendDataLoader 단위 테스트 — repository mock 기반, 실제 DB 호출 없음 (DP-379)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.services.trend.data_loader import TrendDataLoader, TrendRawData


def _make_loader(
    cur_contents: list[dict] | None = None,
    cur_views: dict | None = None,
    prev_views: dict | None = None,
    summary_meta: dict | None = None,
) -> TrendDataLoader:
    content_repo = MagicMock()
    summary_repo = MagicMock()

    content_repo.find_by_published_range.return_value = cur_contents or []
    content_repo.find_view_counts_by_period.side_effect = [
        cur_views if cur_views is not None else {},
        prev_views if prev_views is not None else {},
    ]
    summary_repo.find_meta_by_content_ids.return_value = summary_meta or {}

    loader = TrendDataLoader(content_repo=content_repo, summary_repo=summary_repo)
    loader._content_repo = content_repo
    loader._summary_repo = summary_repo
    return loader


_START = datetime(2026, 4, 14, tzinfo=timezone.utc)
_END = datetime(2026, 4, 21, tzinfo=timezone.utc)


# ── 정상 로드 ─────────────────────────────────────────────────────────────────


def test_load_returns_trend_raw_data() -> None:
    loader = _make_loader(
        cur_contents=[{"id": "cid-1", "title": "테스트"}],
        cur_views={"cid-1": 10},
        prev_views={"cid-1": 5},
        summary_meta={"cid-1": {"tags": ["Python"], "category": "Backend"}},
    )

    result = loader.load(_START, _END)

    assert isinstance(result, TrendRawData)
    assert result.cur_contents == [{"id": "cid-1", "title": "테스트"}]
    assert result.cur_view_counts == {"cid-1": 10}
    assert result.prev_view_counts == {"cid-1": 5}
    assert result.summary_meta == {"cid-1": {"tags": ["Python"], "category": "Backend"}}


# ── prev 기간 계산 ────────────────────────────────────────────────────────────


def test_load_computes_prev_period_correctly() -> None:
    loader = _make_loader()
    loader.load(_START, _END)

    calls = loader._content_repo.find_view_counts_by_period.call_args_list
    # 첫 번째 호출 = cur (start, end)
    assert calls[0].args == (_START, _END)
    # 두 번째 호출 = prev (start - delta, start)
    expected_prev_start = _START - (_END - _START)
    assert calls[1].args == (expected_prev_start, _START)


# ── 빈 콘텐츠 ─────────────────────────────────────────────────────────────────


def test_load_empty_contents_skips_summary_meta() -> None:
    loader = _make_loader(cur_contents=[])

    result = loader.load(_START, _END)

    loader._summary_repo.find_meta_by_content_ids.assert_not_called()
    assert result.summary_meta == {}


# ── prev_contents ────────────────────────────────────────────────────────────


def test_load_returns_prev_contents() -> None:
    loader = _make_loader(cur_contents=[{"id": "cid-1", "title": "현재"}])

    result = loader.load(_START, _END)

    assert hasattr(result, "prev_contents")
    assert isinstance(result.prev_contents, list)


# ── 조회수 0건 ────────────────────────────────────────────────────────────────


def test_load_zero_view_counts_returns_empty_dict() -> None:
    loader = _make_loader(
        cur_contents=[{"id": "cid-1", "title": "테스트"}],
        cur_views={},
        prev_views={},
    )

    result = loader.load(_START, _END)

    assert result.cur_view_counts == {}
    assert result.prev_view_counts == {}
