"""POST /internal/summaries 엔드포인트 테스트 — AllLevelsSummaryService mock 기반 (DP-300)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

_VALID_KEY = "test-internal-key"

_LEVEL_SUMMARY = {
    "core_summary": [{"heading": "개요", "content": "내용 요약."}],
    "key_points": ["포인트1"],
    "study_questions": ["질문1"],
    "next_recommendation": "다음 학습 주제",
    "confidence": 0.85,
}

_VALID_ALL_LEVELS_RESPONSE = {
    "content_id": "test-001",
    "common": {
        "one_line_summary": "Redis TTL 설정 전략",
        "keywords": ["TTL", "캐시 무효화"],
        "tags": ["Redis", "백엔드"],
        "difficulty": "easy",
    },
    "beginner": _LEVEL_SUMMARY,
    "junior": _LEVEL_SUMMARY,
    "mid": _LEVEL_SUMMARY,
    "senior": _LEVEL_SUMMARY,
    "generated_at": "2026-03-23T00:00:00+00:00",
    "thumbnail_url": None,
}

_VALID_BODY = {
    "content_id": "test-001",
    "text": "<h1>제목</h1><p>본문입니다.</p>",
}


@pytest.fixture(autouse=True)
def patch_internal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.deps._INTERNAL_KEY", _VALID_KEY)


@pytest.fixture()
def mock_all_levels_service():
    """AllLevelsSummaryService.summarize_all을 mock 처리한다."""
    from app.schemas.summary import AllLevelsSummaryResponse

    mock_result = AllLevelsSummaryResponse.model_validate(_VALID_ALL_LEVELS_RESPONSE)

    with patch("app.api.internal.router.AllLevelsSummaryService") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.summarize_all.return_value = mock_result
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_summaries_success(
    client: TestClient, mock_all_levels_service: MagicMock
) -> None:
    resp = client.post(
        "/internal/summaries",
        json=_VALID_BODY,
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content_id"] == "test-001"
    assert data["common"]["one_line_summary"] == "Redis TTL 설정 전략"
    assert "beginner" in data
    assert "junior" in data
    assert "mid" in data
    assert "senior" in data


def test_summaries_missing_auth(client: TestClient) -> None:
    resp = client.post("/internal/summaries", json=_VALID_BODY)
    assert resp.status_code == 422


def test_summaries_wrong_auth(client: TestClient) -> None:
    resp = client.post(
        "/internal/summaries",
        json=_VALID_BODY,
        headers={"X-Internal-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_summaries_empty_text(client: TestClient) -> None:
    resp = client.post(
        "/internal/summaries",
        json={**_VALID_BODY, "text": ""},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 422


def test_summaries_saves_to_mongo(
    client: TestClient,
    mock_all_levels_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.internal.router._MONGO_URI", "mongodb://localhost:27017"
    )

    with patch("app.api.internal.router.SummaryRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/summaries",
            json=_VALID_BODY,
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo.save_all_levels.assert_called_once()


def test_summaries_returns_ok_even_if_mongo_fails(
    client: TestClient,
    mock_all_levels_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.internal.router._MONGO_URI", "mongodb://localhost:27017"
    )

    with patch("app.api.internal.router.SummaryRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.save_all_levels.side_effect = Exception("MongoDB 연결 실패")
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/summaries",
            json=_VALID_BODY,
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    assert resp.json()["content_id"] == "test-001"


def test_summaries_skips_mongo_when_uri_empty(
    client: TestClient,
    mock_all_levels_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.internal.router._MONGO_URI", "")

    with patch("app.api.internal.router.SummaryRepository") as mock_repo_cls:
        resp = client.post(
            "/internal/summaries",
            json=_VALID_BODY,
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo_cls.assert_not_called()
