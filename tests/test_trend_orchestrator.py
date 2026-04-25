"""TrendOrchestrator 단위 테스트 — mock 기반, 실제 DB/API 호출 없음 (DP-386)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import AIUpstreamError
from app.schemas.trend import TrendResponse
from app.services.trend.data_loader import TrendRawData
from app.services.trend.orchestrator import TrendOrchestrator, compute_period

# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

_PERIOD_START = date(2026, 4, 14)
_PERIOD_END = date(2026, 4, 21)

_FAKE_CONTENT = {
    "id": "cid-1",
    "title": "Kubernetes 배포 전략",
    "translated_title": None,
    "tags": ["Kubernetes", "Docker"],
    "source_name": "Velog",
    "thumbnail_url": None,
    "category": "Backend",
}


def _make_trend_response(unit: str = "weekly") -> TrendResponse:
    return TrendResponse(
        unit=unit,
        period_start=_PERIOD_START,
        period_end=_PERIOD_END,
        date_label="4월 14일 주간",
        top_posts=[],
        top_posts_summary=None,
        collection_summary=None,
    )


def _make_orchestrator() -> TrendOrchestrator:
    """모든 외부 의존성을 mock 처리한 TrendOrchestrator를 반환한다."""
    with (
        patch("app.services.trend.orchestrator.ContentRepository"),
        patch("app.services.trend.orchestrator.SummaryRepository"),
        patch("app.services.trend.orchestrator.TrendSnapshotRepository"),
        patch("app.services.trend.orchestrator.TrendDataLoader"),
        patch("app.services.trend.orchestrator.KoreanTokenizer"),
        patch("app.services.trend.orchestrator.TopPostsSummaryGenerator"),
        patch("app.services.trend.orchestrator.CollectionSummaryGenerator"),
        patch("app.services.trend.orchestrator.ExternalSignalFetcher"),
    ):
        orch = TrendOrchestrator("postgresql://test", aws_region="us-east-1")

    orch._loader = MagicMock()
    orch._normalizer = MagicMock()
    orch._freq = MagicMock()
    orch._tokenizer = MagicMock()
    orch._tfidf = MagicMock()
    orch._ranker = MagicMock()
    orch._external = MagicMock()
    orch._top_posts_gen = MagicMock()
    orch._collection_gen = MagicMock()
    orch._snapshot_repo = MagicMock()
    return orch


def _setup_defaults(orch: TrendOrchestrator) -> None:
    """기본 mock 반환값 — 정상 흐름."""
    orch._snapshot_repo.get_by_period.return_value = None
    orch._loader.load.return_value = TrendRawData(
        cur_contents=[_FAKE_CONTENT],
        cur_view_counts={"cid-1": 10},
        prev_view_counts={"cid-1": 5},
        prev_contents=[],
    )
    orch._normalizer.normalize.side_effect = lambda tags: tags
    orch._freq.analyze.return_value = []
    orch._tokenizer.tokenize.return_value = ["kubernetes 배포"]
    orch._tfidf.extract.return_value = [("kubernetes", 0.5)]
    orch._ranker.rank_contents.return_value = [_FAKE_CONTENT]
    orch._ranker.rank_tags.return_value = []
    orch._external.fetch.return_value = {}
    orch._top_posts_gen.generate.return_value = "Top posts 요약"
    orch._collection_gen.generate.return_value = "Collection 요약"


# ── 정상 흐름 ──────────────────────────────────────────────────────────────────


def test_run_returns_trend_response() -> None:
    orch = _make_orchestrator()
    _setup_defaults(orch)

    result = orch.run("weekly", _PERIOD_START, _PERIOD_END)

    assert isinstance(result, TrendResponse)
    assert result.unit == "weekly"
    assert result.period_start == _PERIOD_START
    assert result.period_end == _PERIOD_END


def test_run_saves_snapshot() -> None:
    orch = _make_orchestrator()
    _setup_defaults(orch)

    orch.run("weekly", _PERIOD_START, _PERIOD_END)

    orch._snapshot_repo.upsert.assert_called_once()


def test_run_top_posts_populated() -> None:
    orch = _make_orchestrator()
    _setup_defaults(orch)

    result = orch.run("weekly", _PERIOD_START, _PERIOD_END)

    assert len(result.top_posts) == 1
    assert result.top_posts[0].id == "cid-1"
    assert result.top_posts[0].source_name == "Velog"


# ── 스냅샷 skip ────────────────────────────────────────────────────────────────


def test_run_skips_if_snapshot_exists() -> None:
    orch = _make_orchestrator()
    existing = _make_trend_response()
    orch._snapshot_repo.get_by_period.return_value = existing

    result = orch.run("weekly", _PERIOD_START, _PERIOD_END, force=False)

    assert result == existing
    orch._loader.load.assert_not_called()


def test_run_force_regenerates_when_snapshot_exists() -> None:
    orch = _make_orchestrator()
    orch._snapshot_repo.get_by_period.return_value = None
    _setup_defaults(orch)

    orch.run("weekly", _PERIOD_START, _PERIOD_END, force=True)

    orch._loader.load.assert_called_once()
    orch._snapshot_repo.upsert.assert_called_once()


# ── LLM 실패 격리 ──────────────────────────────────────────────────────────────


def test_run_top_posts_summary_failure_still_saves_snapshot() -> None:
    orch = _make_orchestrator()
    _setup_defaults(orch)
    orch._top_posts_gen.generate.side_effect = AIUpstreamError()

    result = orch.run("weekly", _PERIOD_START, _PERIOD_END)

    assert result.top_posts_summary is None
    orch._snapshot_repo.upsert.assert_called_once()


# ── date_label ─────────────────────────────────────────────────────────────────


def test_run_weekly_date_label() -> None:
    orch = _make_orchestrator()
    _setup_defaults(orch)

    result = orch.run("weekly", _PERIOD_START, _PERIOD_END)

    assert "주간" in result.date_label


def test_run_monthly_date_label() -> None:
    orch = _make_orchestrator()
    _setup_defaults(orch)

    result = orch.run("monthly", date(2026, 3, 1), date(2026, 4, 1))

    assert "년" in result.date_label
    assert "월" in result.date_label


def test_run_daily_date_label() -> None:
    orch = _make_orchestrator()
    _setup_defaults(orch)

    result = orch.run("daily", date(2026, 4, 23), date(2026, 4, 24))

    assert "4월" in result.date_label
    assert "주간" not in result.date_label


# ── 빈 콘텐츠 ──────────────────────────────────────────────────────────────────


def test_run_empty_contents_returns_empty_top_posts() -> None:
    orch = _make_orchestrator()
    _setup_defaults(orch)
    orch._loader.load.return_value = TrendRawData(
        cur_contents=[],
        cur_view_counts={},
        prev_view_counts={},
        prev_contents=[],
    )
    orch._ranker.rank_contents.return_value = []

    result = orch.run("weekly", _PERIOD_START, _PERIOD_END)

    assert result.top_posts == []
    orch._snapshot_repo.upsert.assert_called_once()


# ── compute_period ─────────────────────────────────────────────────────────────


def test_compute_period_daily() -> None:
    ref = date(2026, 4, 24)
    start, end = compute_period("daily", ref)

    assert start == date(2026, 4, 23)
    assert end == date(2026, 4, 24)


def test_compute_period_weekly_on_monday() -> None:
    ref = date(2026, 4, 20)  # 월요일
    start, end = compute_period("weekly", ref)

    assert end == date(2026, 4, 20)
    assert start == date(2026, 4, 13)


def test_compute_period_monthly() -> None:
    ref = date(2026, 4, 24)
    start, end = compute_period("monthly", ref)

    assert start == date(2026, 3, 1)
    assert end == date(2026, 4, 1)


def test_compute_period_invalid_unit() -> None:
    with pytest.raises(ValueError):
        compute_period("quarterly")


# ── 캐시 무효화 통합 (DP-387) ──────────────────────────────────────────────────


def _make_orchestrator_with_cache(
    backend_url: str | None, key: str | None
) -> TrendOrchestrator:
    with (
        patch("app.services.trend.orchestrator.ContentRepository"),
        patch("app.services.trend.orchestrator.SummaryRepository"),
        patch("app.services.trend.orchestrator.TrendSnapshotRepository"),
        patch("app.services.trend.orchestrator.TrendDataLoader"),
        patch("app.services.trend.orchestrator.KoreanTokenizer"),
        patch("app.services.trend.orchestrator.TopPostsSummaryGenerator"),
        patch("app.services.trend.orchestrator.CollectionSummaryGenerator"),
        patch("app.services.trend.orchestrator.ExternalSignalFetcher"),
    ):
        orch = TrendOrchestrator(
            "postgresql://test",
            aws_region="us-east-1",
            backend_url=backend_url,
            internal_key=key,
        )
    orch._loader = MagicMock()
    orch._normalizer = MagicMock()
    orch._freq = MagicMock()
    orch._tokenizer = MagicMock()
    orch._tfidf = MagicMock()
    orch._ranker = MagicMock()
    orch._external = MagicMock()
    orch._top_posts_gen = MagicMock()
    orch._collection_gen = MagicMock()
    orch._snapshot_repo = MagicMock()
    return orch


def test_cache_client_created_when_both_params_set() -> None:
    orch = _make_orchestrator_with_cache("http://be:8080", "secret")
    assert orch._cache_client is not None
    assert orch._cache_client._url == "http://be:8080/internal/trends/cache"


def test_cache_client_none_when_key_missing() -> None:
    assert _make_orchestrator_with_cache("http://be:8080", None)._cache_client is None


def test_cache_client_none_when_url_missing() -> None:
    assert _make_orchestrator_with_cache(None, "secret")._cache_client is None


def test_run_calls_cache_eviction_after_upsert() -> None:
    orch = _make_orchestrator_with_cache("http://be:8080", "secret")
    _setup_defaults(orch)

    with patch.object(orch._cache_client, "evict") as mock_evict:
        orch.run("weekly", _PERIOD_START, _PERIOD_END)

    orch._snapshot_repo.upsert.assert_called_once()
    mock_evict.assert_called_once_with("weekly", _PERIOD_START)


def test_run_skips_cache_eviction_when_no_client() -> None:
    orch = _make_orchestrator_with_cache(None, None)
    _setup_defaults(orch)

    orch.run("weekly", _PERIOD_START, _PERIOD_END)

    orch._snapshot_repo.upsert.assert_called_once()


# ── trending_tags (DP-380 / DP-382) ───────────────────────────────────────────


def test_run_trending_tags_empty_when_no_tag_frequencies() -> None:
    orch = _make_orchestrator()
    _setup_defaults(orch)
    orch._ranker.rank_tags.return_value = []

    result = orch.run("weekly", _PERIOD_START, _PERIOD_END)

    assert result.trending_tags == []


def test_run_trending_tags_populated_from_rank_tags() -> None:
    from app.services.trend.ranking import RankedTag

    orch = _make_orchestrator()
    _setup_defaults(orch)
    orch._ranker.rank_tags.return_value = [
        RankedTag(
            keyword="kubernetes",
            cur_count=10,
            prev_count=5,
            delta=5,
            growth_rate=100.0,
            state="up",
            tag_count=10,
            score=4.0,
        )
    ]

    result = orch.run("weekly", _PERIOD_START, _PERIOD_END)

    assert len(result.trending_tags) == 1
    tag = result.trending_tags[0]
    assert tag.keyword == "kubernetes"
    assert tag.count == 10
    assert tag.rank == 1
    assert tag.state == "up"


def test_run_trending_tags_external_failure_still_produces_tags() -> None:
    from app.services.trend.ranking import RankedTag

    orch = _make_orchestrator()
    _setup_defaults(orch)
    orch._external.fetch.side_effect = Exception("외부 API 실패")
    orch._ranker.rank_tags.return_value = [
        RankedTag(
            keyword="docker",
            cur_count=8,
            prev_count=4,
            delta=4,
            growth_rate=100.0,
            state="up",
            tag_count=8,
            score=3.0,
        )
    ]

    result = orch.run("daily", _PERIOD_START, _PERIOD_END)

    assert len(result.trending_tags) == 1
    assert result.trending_tags[0].keyword == "docker"


def test_run_external_fetch_called_with_unit() -> None:
    orch = _make_orchestrator()
    _setup_defaults(orch)

    orch.run("monthly", _PERIOD_START, _PERIOD_END)

    orch._external.fetch.assert_called_once_with("monthly")
