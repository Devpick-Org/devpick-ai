"""POST /internal/similar-questions 엔드포인트 테스트 — SimilarQuestionService mock 기반 (DP-235)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

_VALID_KEY = "test-internal-key"

_VALID_BODY = {
    "text": "useEffect 무한 렌더링 문제가 발생합니다",
}

_MOCK_SIMILAR = {
    "question_id": "q-001",
    "text": "useEffect dependency array 관련 렌더링 이슈",
    "score": 0.87,
    "tags": ["React", "useEffect"],
}


@pytest.fixture(autouse=True)
def patch_internal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.deps._INTERNAL_KEY", _VALID_KEY)


@pytest.fixture(autouse=True)
def patch_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.internal.router._OPENAI_API_KEY", "test-openai-key")


@pytest.fixture()
def mock_similar_service():
    """SimilarQuestionService.search를 mock 처리한다."""
    from app.schemas.similar_question import SimilarQuestion

    mock_result = [SimilarQuestion.model_validate(_MOCK_SIMILAR)]

    with patch("app.api.internal.router.SimilarQuestionService") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.search.return_value = mock_result
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_similar_questions_success(
    client: TestClient, mock_similar_service: MagicMock
) -> None:
    resp = client.post(
        "/internal/similar-questions",
        json=_VALID_BODY,
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["question_id"] == "q-001"
    assert data["results"][0]["score"] == pytest.approx(0.87)


def test_similar_questions_missing_auth(client: TestClient) -> None:
    resp = client.post("/internal/similar-questions", json=_VALID_BODY)
    assert resp.status_code == 422


def test_similar_questions_wrong_auth(client: TestClient) -> None:
    resp = client.post(
        "/internal/similar-questions",
        json=_VALID_BODY,
        headers={"X-Internal-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_similar_questions_empty_text(
    client: TestClient, mock_similar_service: MagicMock
) -> None:
    resp = client.post(
        "/internal/similar-questions",
        json={**_VALID_BODY, "text": ""},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 422


def test_similar_questions_with_question_id(
    client: TestClient, mock_similar_service: MagicMock
) -> None:
    resp = client.post(
        "/internal/similar-questions",
        json={**_VALID_BODY, "question_id": "q-self"},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 200
    _, kwargs = mock_similar_service.search.call_args
    assert kwargs["exclude_question_id"] == "q-self"


def test_similar_questions_custom_top_k(
    client: TestClient, mock_similar_service: MagicMock
) -> None:
    resp = client.post(
        "/internal/similar-questions",
        json={**_VALID_BODY, "top_k": 10},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 200
    _, kwargs = mock_similar_service.search.call_args
    assert kwargs["top_k"] == 10


def test_similar_questions_returns_empty_results(
    client: TestClient, mock_similar_service: MagicMock
) -> None:
    mock_similar_service.search.return_value = []

    resp = client.post(
        "/internal/similar-questions",
        json=_VALID_BODY,
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert data["total"] == 0


def test_similar_questions_no_openai_key(
    client: TestClient,
    mock_similar_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.internal.router._OPENAI_API_KEY", "")

    resp = client.post(
        "/internal/similar-questions",
        json=_VALID_BODY,
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 400
