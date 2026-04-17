"""DELETE /internal/questions/{question_id} — 질문 문서 정리 (멱등 204)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app

_VALID_KEY = "test-internal-key"


@pytest.fixture(autouse=True)
def patch_internal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.deps._INTERNAL_KEY", _VALID_KEY)


@pytest.fixture(autouse=True)
def patch_aws_region(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.internal.router._AWS_REGION", "ap-northeast-2")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_delete_question_documents_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []

    def fake_cleanup(qid: str, region: str) -> None:
        called.append(qid)

    monkeypatch.setattr(
        "app.api.internal.router.cleanup_question_documents", fake_cleanup
    )

    qid = "550e8400-e29b-41d4-a716-446655440000"
    resp = client.delete(
        f"/internal/questions/{qid}",
        headers={"X-Internal-Key": _VALID_KEY},
    )
    assert resp.status_code == 204
    assert resp.content == b""
    assert called == [qid]


def test_delete_question_documents_idempotent_mocked(client: TestClient) -> None:
    with patch("app.api.internal.router.cleanup_question_documents") as mock_cleanup:
        resp = client.delete(
            "/internal/questions/00000000-0000-0000-0000-000000000000",
            headers={"X-Internal-Key": _VALID_KEY},
        )
        assert resp.status_code == 204
        mock_cleanup.assert_called_once()


def test_delete_question_missing_auth(client: TestClient) -> None:
    resp = client.delete("/internal/questions/550e8400-e29b-41d4-a716-446655440000")
    assert resp.status_code == 422


def test_delete_question_wrong_auth(client: TestClient) -> None:
    resp = client.delete(
        "/internal/questions/550e8400-e29b-41d4-a716-446655440000",
        headers={"X-Internal-Key": "wrong"},
    )
    assert resp.status_code == 401
