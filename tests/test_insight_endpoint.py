"""POST /internal/report 엔드포인트 테스트 (DP-259)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

_VALID_KEY = "test-internal-key"

_VALID_INSIGHT_RESPONSE = {
    "report_id": "report-001",
    "well_done": "이번 주에 Redis와 Spring Boot 관련 글 5편을 읽었습니다.",
    "lacking": "다만 주중 특정 요일에 활동이 집중되었습니다.",
    "next_week": "다음 주에는 Docker 관련 학습을 이어가보세요.",
    "generated_at": "2026-03-23T00:00:00+00:00",
}

_VALID_BODY = {
    "report_id": "report-001",
    "user_id": "user-001",
    "week_start": "2026-03-17",
    "week_end": "2026-03-23",
    "activities": {
        "contents_read": 5,
        "questions_created": 2,
        "scraps_count": 3,
        "read_content_ids": ["c1", "c2"],
        "scrapped_content_ids": ["c1"],
        "question_ids": ["q1"],
    },
}


@pytest.fixture(autouse=True)
def patch_internal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.deps._INTERNAL_KEY", _VALID_KEY)


@pytest.fixture()
def mock_insight_service():
    """InsightService.generate를 mock 처리한다."""
    from app.schemas.insight import InsightResponse

    mock_result = InsightResponse.model_validate(_VALID_INSIGHT_RESPONSE)

    with patch("app.api.internal.router.InsightService") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.generate.return_value = mock_result
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_report_success(client: TestClient, mock_insight_service: MagicMock) -> None:
    resp = client.post(
        "/internal/report",
        json=_VALID_BODY,
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_id"] == "report-001"
    assert data["well_done"].startswith("이번 주에")
    assert data["lacking"].startswith("다만")
    assert data["next_week"].startswith("다음 주에는")
    assert "generated_at" in data


def test_report_missing_auth(client: TestClient) -> None:
    resp = client.post("/internal/report", json=_VALID_BODY)
    assert resp.status_code == 422


def test_report_wrong_auth(client: TestClient) -> None:
    resp = client.post(
        "/internal/report",
        json=_VALID_BODY,
        headers={"X-Internal-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_report_returns_ok_even_if_dynamo_fails(
    client: TestClient,
    mock_insight_service: MagicMock,
) -> None:
    with patch("app.api.internal.router.InsightRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.save.side_effect = Exception("DynamoDB 연결 실패")
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/report",
            json=_VALID_BODY,
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    assert resp.json()["report_id"] == "report-001"


def test_report_saves_to_dynamo(
    client: TestClient,
    mock_insight_service: MagicMock,
) -> None:
    with (
        patch("app.api.internal.router.InsightRepository") as mock_insight_repo,
        patch("app.api.internal.router.EventRepository"),
        patch("app.api.internal.router.SummaryRepository"),
        patch("app.api.internal.router.QuestionVectorRepository"),
    ):
        mock_repo = MagicMock()
        mock_insight_repo.return_value = mock_repo

        resp = client.post(
            "/internal/report",
            json=_VALID_BODY,
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo.save.assert_called_once()


def test_report_injects_report_id(
    client: TestClient,
    mock_insight_service: MagicMock,
) -> None:
    """generate() 반환값에 report_id가 올바르게 주입된다."""
    resp = client.post(
        "/internal/report",
        json={**_VALID_BODY, "report_id": "my-report-xyz"},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["report_id"] == "my-report-xyz"
