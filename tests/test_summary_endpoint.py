"""POST /internal/summary 엔드포인트 테스트 — SummaryService mock 기반 (DP-217, DP-220)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

_VALID_KEY = "test-internal-key"

_VALID_SUMMARY_RESPONSE = {
    "content_id": "test-001",
    "level": "junior",
    "one_line_summary": "Redis TTL 설정 전략",
    "core_summary": [
        {"heading": "캐시 무효화", "content": "TTL로 자동 삭제된다."},
    ],
    "key_points": ["TTL 설정"],
    "keywords": ["캐시 무효화", "TTL"],
    "tags": ["Redis"],
    "difficulty": "easy",
    "next_recommendation": "Pub/Sub 패턴도 학습해보세요.",
    "study_questions": ["TTL이란?"],
    "confidence": 0.9,
    "generated_at": "2026-03-16T00:00:00+00:00",
    "thumbnail_url": None,
}

_VALID_BODY = {
    "content_id": "test-001",
    "level": "JUNIOR",
    "text": "<h1>제목</h1><p>본문입니다.</p>",
}


@pytest.fixture(autouse=True)
def patch_internal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.deps._INTERNAL_KEY", _VALID_KEY)


@pytest.fixture()
def mock_summary_service():
    """SummaryService.summarize를 mock 처리한다."""
    from app.schemas.summary import SummaryResponse

    mock_result = SummaryResponse.model_validate(_VALID_SUMMARY_RESPONSE)

    with patch("app.api.internal.router.SummaryService") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.summarize.return_value = mock_result
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_summary_success(client: TestClient, mock_summary_service: MagicMock) -> None:
    resp = client.post(
        "/internal/summary",
        json=_VALID_BODY,
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content_id"] == "test-001"
    assert data["level"] == "junior"
    assert data["one_line_summary"] == "Redis TTL 설정 전략"


def test_summary_level_mapping_upper(
    client: TestClient, mock_summary_service: MagicMock
) -> None:
    client.post(
        "/internal/summary",
        json={**_VALID_BODY, "level": "JUNIOR"},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    mock_summary_service.summarize.assert_called_once()
    _, kwargs = mock_summary_service.summarize.call_args
    assert kwargs["level"] == "junior"


def test_summary_level_mapping_middle(
    client: TestClient, mock_summary_service: MagicMock
) -> None:
    from app.schemas.summary import SummaryResponse

    mid_response = SummaryResponse.model_validate(
        {**_VALID_SUMMARY_RESPONSE, "level": "mid"}
    )
    mock_summary_service.summarize.return_value = mid_response

    client.post(
        "/internal/summary",
        json={**_VALID_BODY, "level": "MIDDLE"},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    mock_summary_service.summarize.assert_called_once()
    _, kwargs = mock_summary_service.summarize.call_args
    assert kwargs["level"] == "mid"


def test_summary_level_mapping_lower(
    client: TestClient, mock_summary_service: MagicMock
) -> None:
    client.post(
        "/internal/summary",
        json={**_VALID_BODY, "level": "junior"},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    mock_summary_service.summarize.assert_called_once()
    _, kwargs = mock_summary_service.summarize.call_args
    assert kwargs["level"] == "junior"


def test_summary_missing_auth(client: TestClient) -> None:
    resp = client.post("/internal/summary", json=_VALID_BODY)
    assert resp.status_code == 422


def test_summary_wrong_auth(client: TestClient) -> None:
    resp = client.post(
        "/internal/summary",
        json=_VALID_BODY,
        headers={"X-Internal-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_summary_empty_text(client: TestClient) -> None:
    resp = client.post(
        "/internal/summary",
        json={**_VALID_BODY, "text": ""},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 422


def test_summary_invalid_level(client: TestClient) -> None:
    resp = client.post(
        "/internal/summary",
        json={**_VALID_BODY, "level": "EXPERT"},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 400


# --- DP-220: MongoDB 저장 관련 테스트 ---


def test_summary_saves_to_mongo(
    client: TestClient, mock_summary_service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.internal.router._MONGO_URI", "mongodb://localhost:27017"
    )

    with patch("app.api.internal.router.SummaryRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/summary",
            json=_VALID_BODY,
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo.save.assert_called_once()


def test_summary_returns_ok_even_if_mongo_fails(
    client: TestClient, mock_summary_service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.internal.router._MONGO_URI", "mongodb://localhost:27017"
    )

    with patch("app.api.internal.router.SummaryRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.save.side_effect = Exception("MongoDB connection failed")
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/summary",
            json=_VALID_BODY,
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    assert resp.json()["content_id"] == "test-001"


def test_summary_skips_mongo_when_uri_empty(
    client: TestClient, mock_summary_service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.internal.router._MONGO_URI", "")

    with patch("app.api.internal.router.SummaryRepository") as mock_repo_cls:
        resp = client.post(
            "/internal/summary",
            json=_VALID_BODY,
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo_cls.assert_not_called()
