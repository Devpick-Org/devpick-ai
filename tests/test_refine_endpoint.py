"""POST /internal/refine 엔드포인트 테스트 — RefineService mock 기반 (DP-231)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

_VALID_KEY = "test-internal-key"

_VALID_REFINE_RESPONSE = {
    "refined_title": "Redis TTL 설정 방법과 EXPIRE 명령 사용법",
    "refined_content": "Redis에서 TTL을 설정하여 캐시 키 자동 만료를 구현하고 싶습니다.",
    "suggested_tags": ["Redis", "캐시"],
    "confidence": 0.85,
    "generated_at": "2026-03-19T00:00:00+00:00",
}

_VALID_BODY = {
    "title": "redis ttl",
    "content": "redis ttl이 뭔가요",
}


@pytest.fixture(autouse=True)
def patch_internal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.deps._INTERNAL_KEY", _VALID_KEY)


@pytest.fixture()
def mock_refine_service():
    """RefineService.refine을 mock 처리한다."""
    from app.schemas.refine import RefineResponse

    mock_result = RefineResponse.model_validate(_VALID_REFINE_RESPONSE)

    with patch("app.api.internal.router.RefineService") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.refine.return_value = mock_result
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_refine_success(client: TestClient, mock_refine_service: MagicMock) -> None:
    resp = client.post(
        "/internal/refine",
        json=_VALID_BODY,
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["refined_title"] == _VALID_REFINE_RESPONSE["refined_title"]
    assert data["confidence"] == pytest.approx(0.85)


def test_refine_missing_auth(client: TestClient) -> None:
    resp = client.post("/internal/refine", json=_VALID_BODY)
    assert resp.status_code == 422


def test_refine_wrong_auth(client: TestClient) -> None:
    resp = client.post(
        "/internal/refine",
        json=_VALID_BODY,
        headers={"X-Internal-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_refine_empty_title(client: TestClient) -> None:
    resp = client.post(
        "/internal/refine",
        json={**_VALID_BODY, "title": ""},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 422


def test_refine_empty_content(client: TestClient) -> None:
    resp = client.post(
        "/internal/refine",
        json={**_VALID_BODY, "content": ""},
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 422


# --- content_id + MongoDB 컨텍스트 조회 관련 테스트 ---


def test_refine_with_content_id_fetches_chunks(
    client: TestClient,
    mock_refine_service: MagicMock,
) -> None:
    mock_chunks = [
        {"text": "Redis EXPIRE 명령으로 키에 TTL을 설정한다.", "chunk_index": 0},
        {"text": "TTL이 지나면 자동 삭제된다.", "chunk_index": 1},
    ]

    with patch("app.api.internal.router.VectorRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.find_by_content_id.return_value = mock_chunks
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/refine",
            json={**_VALID_BODY, "content_id": "cid-001"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo.find_by_content_id.assert_called_once_with("cid-001")
    _, kwargs = mock_refine_service.refine.call_args
    assert kwargs["context_chunks"] == [
        "Redis EXPIRE 명령으로 키에 TTL을 설정한다.",
        "TTL이 지나면 자동 삭제된다.",
    ]


def test_refine_without_content_id_skips_dynamo(
    client: TestClient,
    mock_refine_service: MagicMock,
) -> None:
    with patch("app.api.internal.router.VectorRepository") as mock_repo_cls:
        resp = client.post(
            "/internal/refine",
            json=_VALID_BODY,  # content_id 없음
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo_cls.assert_not_called()
    _, kwargs = mock_refine_service.refine.call_args
    assert kwargs["context_chunks"] is None


def test_refine_returns_ok_even_if_dynamo_fails(
    client: TestClient,
    mock_refine_service: MagicMock,
) -> None:
    with patch("app.api.internal.router.VectorRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.find_by_content_id.side_effect = Exception(
            "MongoDB connection failed"
        )
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/refine",
            json={**_VALID_BODY, "content_id": "cid-001"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    _, kwargs = mock_refine_service.refine.call_args
    assert kwargs["context_chunks"] is None


def test_refine_with_content_id_always_queries_dynamo(
    client: TestClient,
    mock_refine_service: MagicMock,
) -> None:
    """content_id가 있으면 항상 DynamoDB에서 청크를 조회한다."""
    with patch("app.api.internal.router.VectorRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.find_by_content_id.return_value = []
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/refine",
            json={**_VALID_BODY, "content_id": "cid-001"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo.find_by_content_id.assert_called_once_with("cid-001")
