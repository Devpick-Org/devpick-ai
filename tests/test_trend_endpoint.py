"""POST/GET /internal/trends 엔드포인트 테스트 — mock 기반 (DP-385)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.schemas.trend import TrendResponse
from main import app

_VALID_KEY = "test-internal-key"
_DATABASE_URL = "postgresql://mock"

_TREND_RESPONSE = TrendResponse(
    unit="weekly",
    period_start=date(2026, 4, 14),
    period_end=date(2026, 4, 21),
    date_label="4월 14일 주간",
    top_posts=[],
    top_posts_summary="주간 Top 5 서사 요약",
    collection_summary="수집 동향 요약",
)


@pytest.fixture(autouse=True)
def patch_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.deps._INTERNAL_KEY", _VALID_KEY)
    monkeypatch.setattr("app.api.internal.router._DATABASE_URL", _DATABASE_URL)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ── POST /internal/trends ─────────────────────────────────────────────────────


def test_create_trend_success(client: TestClient) -> None:
    with (
        patch("app.api.internal.router.ContentRepository") as mock_repo_cls,
        patch("app.api.internal.router.TrendOrchestrator") as mock_orch_cls,
    ):
        mock_repo = MagicMock()
        mock_repo.count_by_published_range.return_value = 10
        mock_repo_cls.return_value = mock_repo

        mock_orch = MagicMock()
        mock_orch.run.return_value = _TREND_RESPONSE
        mock_orch_cls.return_value = mock_orch

        resp = client.post(
            "/internal/trends",
            json={"unit": "weekly", "period_start": "2026-04-14"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["unit"] == "weekly"
    assert data["period_start"] == "2026-04-14"
    assert data["top_posts_summary"] == "주간 Top 5 서사 요약"


def test_create_trend_auto_period(client: TestClient) -> None:
    """period_start 미입력 시 compute_period로 자동 계산한다."""
    with (
        patch(
            "app.api.internal.router.compute_period",
            return_value=(date(2026, 4, 14), date(2026, 4, 21)),
        ),
        patch("app.api.internal.router.ContentRepository") as mock_repo_cls,
        patch("app.api.internal.router.TrendOrchestrator") as mock_orch_cls,
    ):
        mock_repo = MagicMock()
        mock_repo.count_by_published_range.return_value = 10
        mock_repo_cls.return_value = mock_repo

        mock_orch = MagicMock()
        mock_orch.run.return_value = _TREND_RESPONSE
        mock_orch_cls.return_value = mock_orch

        resp = client.post(
            "/internal/trends",
            json={"unit": "weekly"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200


def test_create_trend_zero_contents_returns_400(client: TestClient) -> None:
    with patch("app.api.internal.router.ContentRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.count_by_published_range.return_value = 0
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/trends",
            json={"unit": "daily"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 400


def test_create_trend_few_contents_returns_422(client: TestClient) -> None:
    with patch("app.api.internal.router.ContentRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.count_by_published_range.return_value = 3
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/trends",
            json={"unit": "weekly"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 422


def test_create_trend_invalid_unit_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/internal/trends",
        json={"unit": "hourly"},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 422


def test_create_trend_missing_auth_returns_422(client: TestClient) -> None:
    resp = client.post("/internal/trends", json={"unit": "daily"})
    assert resp.status_code == 422


def test_create_trend_force_refresh_calls_run_with_force_true(
    client: TestClient,
) -> None:
    with (
        patch("app.api.internal.router.ContentRepository") as mock_repo_cls,
        patch("app.api.internal.router.TrendOrchestrator") as mock_orch_cls,
    ):
        mock_repo = MagicMock()
        mock_repo.count_by_published_range.return_value = 10
        mock_repo_cls.return_value = mock_repo

        mock_orch = MagicMock()
        mock_orch.run.return_value = _TREND_RESPONSE
        mock_orch_cls.return_value = mock_orch

        client.post(
            "/internal/trends",
            json={
                "unit": "weekly",
                "period_start": "2026-04-14",
                "force_refresh": True,
            },
            headers={"X-Internal-Key": _VALID_KEY},
        )

        _, kwargs = mock_orch.run.call_args
        assert kwargs.get("force") is True or mock_orch.run.call_args[0][3] is True


# ── GET /internal/trends/latest ──────────────────────────────────────────────


def test_get_latest_trend_success(client: TestClient) -> None:
    with patch("app.api.internal.router.TrendSnapshotRepository") as mock_cls:
        mock_repo = MagicMock()
        mock_repo.get_latest.return_value = _TREND_RESPONSE
        mock_cls.return_value = mock_repo

        resp = client.get(
            "/internal/trends/latest?unit=weekly",
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    assert resp.json()["unit"] == "weekly"


def test_get_latest_trend_not_found(client: TestClient) -> None:
    with patch("app.api.internal.router.TrendSnapshotRepository") as mock_cls:
        mock_repo = MagicMock()
        mock_repo.get_latest.return_value = None
        mock_cls.return_value = mock_repo

        resp = client.get(
            "/internal/trends/latest?unit=daily",
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 404


def test_get_latest_trend_missing_auth(client: TestClient) -> None:
    resp = client.get("/internal/trends/latest?unit=weekly")
    assert resp.status_code == 422


# ── GET /internal/trends/{period_start} ──────────────────────────────────────


def test_get_trend_by_period_success(client: TestClient) -> None:
    with patch("app.api.internal.router.TrendSnapshotRepository") as mock_cls:
        mock_repo = MagicMock()
        mock_repo.get_by_period.return_value = _TREND_RESPONSE
        mock_cls.return_value = mock_repo

        resp = client.get(
            "/internal/trends/2026-04-14?unit=weekly",
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    assert resp.json()["period_start"] == "2026-04-14"


def test_get_trend_by_period_not_found(client: TestClient) -> None:
    with patch("app.api.internal.router.TrendSnapshotRepository") as mock_cls:
        mock_repo = MagicMock()
        mock_repo.get_by_period.return_value = None
        mock_cls.return_value = mock_repo

        resp = client.get(
            "/internal/trends/2026-04-14?unit=weekly",
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 404


def test_get_trend_by_period_invalid_date(client: TestClient) -> None:
    resp = client.get(
        "/internal/trends/not-a-date?unit=weekly",
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 422
