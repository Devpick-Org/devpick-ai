"""TrendSnapshotRepository 단위 테스트 — SQLAlchemy mock 기반, 실제 DB 호출 없음."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from app.repositories.trend_repository import TrendSnapshotRepository
from app.schemas.trend import TopContent, TrendResponse


def _make_repo() -> tuple[TrendSnapshotRepository, MagicMock]:
    with patch("app.repositories.trend_repository.create_engine") as mock_engine_fn:
        mock_engine = MagicMock()
        mock_engine_fn.return_value = mock_engine
        repo = TrendSnapshotRepository(database_url="postgresql://test/db")
    repo._engine = mock_engine
    return repo, mock_engine


def _setup_conn(mock_engine: MagicMock) -> MagicMock:
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)
    return mock_conn


def _make_trend_response() -> TrendResponse:
    return TrendResponse(
        unit="weekly",
        period_start=date(2026, 4, 14),
        period_end=date(2026, 4, 20),
        date_label="2026-04-14 ~ 2026-04-20",
        top_posts=[
            TopContent(
                id="content-uuid-1",
                title="테스트 글",
                source_name="Kakao_Tech",
            )
        ],
        top_posts_summary="주간 동향 요약",
        collection_summary="수집 동향 요약",
    )


# ── upsert ────────────────────────────────────────────────────────────────────


def test_upsert_inserts_new_record() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = _setup_conn(mock_engine)
    trend = _make_trend_response()
    now = datetime.now(tz=timezone.utc)

    repo.upsert("weekly", "global", trend.period_start, trend.period_end, trend, now)

    mock_conn.execute.assert_called_once()
    sql = mock_conn.execute.call_args[0][0].text
    assert "ON CONFLICT" in sql
    assert "DO UPDATE" in sql


def test_upsert_includes_correct_params() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = _setup_conn(mock_engine)
    trend = _make_trend_response()
    now = datetime.now(tz=timezone.utc)

    repo.upsert("weekly", "global", trend.period_start, trend.period_end, trend, now)

    params = mock_conn.execute.call_args[0][1]
    assert params["unit"] == "weekly"
    assert params["scope"] == "global"
    assert params["period_start"] == trend.period_start
    assert params["period_end"] == trend.period_end
    assert params["generated_at"] == now
    assert "top_posts" in params["payload"]


def test_upsert_expires_at_nullable() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = _setup_conn(mock_engine)
    trend = _make_trend_response()
    now = datetime.now(tz=timezone.utc)

    repo.upsert(
        "weekly",
        "global",
        trend.period_start,
        trend.period_end,
        trend,
        now,
        expires_at=None,
    )

    params = mock_conn.execute.call_args[0][1]
    assert params["expires_at"] is None


# ── get_latest ────────────────────────────────────────────────────────────────


def test_get_latest_returns_trend_response() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = _setup_conn(mock_engine)
    trend = _make_trend_response()
    payload_json = trend.model_dump_json()

    row = MagicMock()
    row.__getitem__ = lambda self, i: payload_json
    mock_conn.execute.return_value.fetchone.return_value = row

    result = repo.get_latest("weekly")

    assert result is not None
    assert result.unit == "weekly"
    assert result.date_label == "2026-04-14 ~ 2026-04-20"
    assert len(result.top_posts) == 1


def test_get_latest_returns_none_when_empty() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = _setup_conn(mock_engine)
    mock_conn.execute.return_value.fetchone.return_value = None

    result = repo.get_latest("weekly")

    assert result is None


# ── get_by_period ─────────────────────────────────────────────────────────────


def test_get_by_period_returns_trend_response() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = _setup_conn(mock_engine)
    trend = _make_trend_response()
    payload_json = trend.model_dump_json()

    row = MagicMock()
    row.__getitem__ = lambda self, i: payload_json
    mock_conn.execute.return_value.fetchone.return_value = row

    result = repo.get_by_period("weekly", "global", date(2026, 4, 14))

    assert result is not None
    assert result.period_start == date(2026, 4, 14)
    assert result.top_posts_summary == "주간 동향 요약"


def test_get_by_period_returns_none_when_empty() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = _setup_conn(mock_engine)
    mock_conn.execute.return_value.fetchone.return_value = None

    result = repo.get_by_period("weekly", "global", date(2026, 4, 14))

    assert result is None
