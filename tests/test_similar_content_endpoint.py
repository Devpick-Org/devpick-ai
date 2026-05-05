"""POST /internal/similar-contents 엔드포인트 통합 테스트 (DP-288)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

_HEADERS = {"X-Internal-Key": "test-internal-key"}


@pytest.fixture(autouse=True)
def mock_internal_key(monkeypatch):
    monkeypatch.setattr("app.api.deps._INTERNAL_KEY", "test-internal-key")


@pytest.fixture()
def mock_service():
    with patch("app.api.internal.router.SimilarContentService") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_similar_contents_success(client, mock_service) -> None:
    from app.schemas.similar_content import SimilarContent

    mock_service.search.return_value = [
        SimilarContent(content_id="article-001", score=0.92),
        SimilarContent(content_id="article-002", score=0.75),
    ]

    resp = client.post(
        "/internal/similar-contents",
        headers=_HEADERS,
        json={"text": "React 상태 관리 방법"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["results"][0]["content_id"] == "article-001"
    assert data["results"][0]["score"] == pytest.approx(0.92)


def test_similar_contents_empty_results(client, mock_service) -> None:
    mock_service.search.return_value = []

    resp = client.post(
        "/internal/similar-contents",
        headers=_HEADERS,
        json={"text": "존재하지 않는 주제"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert data["total"] == 0


def test_similar_contents_missing_auth(client, mock_service) -> None:
    resp = client.post(
        "/internal/similar-contents",
        json={"text": "React 상태 관리"},
    )
    assert resp.status_code == 422


def test_similar_contents_wrong_auth(client, mock_service) -> None:
    resp = client.post(
        "/internal/similar-contents",
        headers={"X-Internal-Key": "wrong-key"},
        json={"text": "React 상태 관리"},
    )
    assert resp.status_code == 401


def test_similar_contents_empty_text(client, mock_service) -> None:
    resp = client.post(
        "/internal/similar-contents",
        headers=_HEADERS,
        json={"text": ""},
    )
    assert resp.status_code == 422


def test_similar_contents_passes_content_id(client, mock_service) -> None:
    mock_service.search.return_value = []

    client.post(
        "/internal/similar-contents",
        headers=_HEADERS,
        json={"text": "쿼리", "content_id": "article-self"},
    )

    mock_service.search.assert_called_once_with(
        text="쿼리",
        top_k=20,
        min_score=0.5,
        exclude_content_id="article-self",
    )


def test_similar_contents_custom_top_k(client, mock_service) -> None:
    mock_service.search.return_value = []

    client.post(
        "/internal/similar-contents",
        headers=_HEADERS,
        json={"text": "쿼리", "top_k": 10},
    )

    mock_service.search.assert_called_once_with(
        text="쿼리",
        top_k=10,
        min_score=0.5,
        exclude_content_id=None,
    )


def test_similar_contents_event_logged_when_user_id_present(
    client, mock_service
) -> None:
    mock_service.search.return_value = []

    with patch("app.api.internal.router.EventRepository") as mock_event_repo_cls:
        mock_event_repo = MagicMock()
        mock_event_repo_cls.return_value = mock_event_repo

        client.post(
            "/internal/similar-contents",
            headers=_HEADERS,
            json={"text": "쿼리", "user_id": "user-001"},
        )

    mock_event_repo.save_event.assert_called_once()


def test_similar_contents_no_event_when_user_id_absent(client, mock_service) -> None:
    mock_service.search.return_value = []

    with patch("app.api.internal.router.EventRepository") as mock_event_repo_cls:
        mock_event_repo = MagicMock()
        mock_event_repo_cls.return_value = mock_event_repo

        client.post(
            "/internal/similar-contents",
            headers=_HEADERS,
            json={"text": "쿼리"},
        )

    mock_event_repo.save_event.assert_not_called()
