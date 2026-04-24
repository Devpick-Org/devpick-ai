"""CacheEvictionClient 단위 테스트 (DP-387)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from app.services.trend.cache_eviction import CacheEvictionClient


def _client(base_url: str = "http://backend:8080", key: str = "test-key") -> CacheEvictionClient:
    return CacheEvictionClient(base_url, key)


# ── URL 조합 ───────────────────────────────────────────────────────────────────


def test_url_built_from_base_url() -> None:
    assert _client("http://backend:8080")._url == "http://backend:8080/internal/trends/cache"


def test_trailing_slash_stripped() -> None:
    assert _client("http://backend:8080/")._url == "http://backend:8080/internal/trends/cache"


# ── 성공 케이스 ────────────────────────────────────────────────────────────────


def test_evict_calls_delete_with_correct_params() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    with patch("requests.delete", return_value=mock_resp) as mock_delete:
        _client().evict("daily", date(2026, 4, 25))

    mock_delete.assert_called_once_with(
        "http://backend:8080/internal/trends/cache",
        headers={"X-Internal-Key": "test-key"},
        params={"unit": "daily", "scope": "global", "periodStart": "2026-04-25"},
        timeout=5.0,
    )


def test_evict_scope_default_global() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 204

    with patch("requests.delete", return_value=mock_resp) as mock_delete:
        _client().evict("weekly", date(2026, 4, 21))

    call_params = mock_delete.call_args.kwargs["params"]
    assert call_params["scope"] == "global"


# ── best-effort: 실패해도 예외 미전파 ─────────────────────────────────────────


def test_non_204_response_does_not_raise() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"

    with patch("requests.delete", return_value=mock_resp):
        _client().evict("daily", date(2026, 4, 25))  # 예외 없어야 함


def test_404_response_does_not_raise() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"

    with patch("requests.delete", return_value=mock_resp):
        _client().evict("monthly", date(2026, 4, 1))


def test_network_error_does_not_raise() -> None:
    with patch("requests.delete", side_effect=ConnectionError("refused")):
        _client().evict("weekly", date(2026, 4, 21))


def test_timeout_error_does_not_raise() -> None:
    import requests as req

    with patch("requests.delete", side_effect=req.Timeout("timeout")):
        _client().evict("daily", date(2026, 4, 25))


