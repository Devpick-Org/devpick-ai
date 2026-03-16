"""POST /internal/summary 에러 시나리오별 HTTP 상태코드 통합 테스트 (DP-223).

TestClient로 실제 FastAPI 앱을 실행하고, SummaryService.summarize를 patch하여
각 에러 상황에서 올바른 HTTP 상태코드가 반환되는지 확인한다.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AIBadRequestError,
    AIInternalError,
    AITimeoutError,
    AIUpstreamError,
)
from main import app

_VALID_BODY = {
    "content_id": "art-001",
    "level": "junior",
    "text": "Redis TTL에 대한 글입니다.",
}

_INTERNAL_KEY = "test-internal-key"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """인증 키를 고정하고 TestClient를 반환한다."""
    import app.api.deps as deps_module
    import app.api.internal.router as router_module

    monkeypatch.setattr(deps_module, "_INTERNAL_KEY", _INTERNAL_KEY)
    monkeypatch.setattr(router_module, "_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(router_module, "_MONGO_URI", "")  # MongoDB 저장 skip

    return TestClient(app, raise_server_exceptions=False)


def _post_with_error(client: TestClient, side_effect: Exception) -> int:
    """SummaryService.summarize를 side_effect로 대체하고 HTTP 상태코드를 반환한다."""
    with patch(
        "app.api.internal.router.SummaryService.summarize", side_effect=side_effect
    ):
        resp = client.post(
            "/internal/summary",
            json=_VALID_BODY,
            headers={"X-Internal-Key": _INTERNAL_KEY},
        )
    return resp.status_code


def test_timeout_returns_504(client: TestClient) -> None:
    assert _post_with_error(client, AITimeoutError()) == 504


def test_rate_limit_returns_502(client: TestClient) -> None:
    assert _post_with_error(client, AIUpstreamError("LLM Rate Limit 초과입니다")) == 502


def test_connection_error_returns_502(client: TestClient) -> None:
    assert _post_with_error(client, AIUpstreamError("LLM 연결에 실패했습니다")) == 502


def test_auth_error_returns_500(client: TestClient) -> None:
    assert _post_with_error(client, AIInternalError("LLM 인증에 실패했습니다")) == 500


def test_invalid_input_returns_400(client: TestClient) -> None:
    assert (
        _post_with_error(client, AIBadRequestError("지원하지 않는 레벨: expert")) == 400
    )


def test_error_response_has_detail_field(client: TestClient) -> None:
    """에러 응답에 detail 필드가 포함되어 있는지 확인한다."""
    with patch(
        "app.api.internal.router.SummaryService.summarize",
        side_effect=AITimeoutError(),
    ):
        resp = client.post(
            "/internal/summary",
            json=_VALID_BODY,
            headers={"X-Internal-Key": _INTERNAL_KEY},
        )

    assert resp.status_code == 504
    assert "detail" in resp.json()
