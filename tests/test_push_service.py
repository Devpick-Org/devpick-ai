"""Unit tests for PushService — mocks HTTP to test push behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.schemas.normalized_content import NormalizedContent
from app.services.push_service import PushService


def make_item(
    source: str = "NAVER_D2", url: str = "https://example.com/1"
) -> NormalizedContent:
    return NormalizedContent(
        source_name=source,
        title="Test Title",
        canonical_url=url,
        published_at="2026-03-12T00:00:00+00:00",
        preview="Short preview text.",
        body_candidate=None,
        body_source="none",
        content_kind="preview_only",
        entry_external_id="ext-001",
    )


def test_push_success_returns_backend_response() -> None:
    service = PushService(backend_url="http://localhost:8080")
    items = [make_item()]

    mock_response = MagicMock()
    mock_response.json.return_value = {"saved": 1, "skipped": 0}
    mock_response.raise_for_status.return_value = None

    with patch(
        "app.services.push_service.requests.post", return_value=mock_response
    ) as mock_post:
        result = service.push(items)

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.args[0] == "http://localhost:8080/internal/contents"
    assert len(call_kwargs.kwargs["json"]) == 1
    assert result == {"saved": 1, "skipped": 0}


def test_push_empty_list_skips_http_call() -> None:
    service = PushService(backend_url="http://localhost:8080")

    with patch("app.services.push_service.requests.post") as mock_post:
        result = service.push([])

    mock_post.assert_not_called()
    assert result == {"saved": 0, "skipped": 0}


def test_push_raises_on_http_error() -> None:
    service = PushService(backend_url="http://localhost:8080")
    items = [make_item()]

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError(
        "422 Unprocessable Entity"
    )

    with patch("app.services.push_service.requests.post", return_value=mock_response):
        with pytest.raises(requests.HTTPError):
            service.push(items)


def test_push_raises_on_server_error() -> None:
    service = PushService(backend_url="http://localhost:8080")
    items = [make_item()]

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError(
        "500 Internal Server Error"
    )

    with patch("app.services.push_service.requests.post", return_value=mock_response):
        with pytest.raises(requests.HTTPError):
            service.push(items)


def test_push_raises_on_timeout() -> None:
    service = PushService(backend_url="http://localhost:8080", timeout=5)
    items = [make_item()]

    with patch(
        "app.services.push_service.requests.post",
        side_effect=requests.Timeout("timed out"),
    ):
        with pytest.raises(requests.Timeout):
            service.push(items)


def test_push_sends_all_items_as_json_payload() -> None:
    service = PushService(backend_url="http://localhost:8080")
    items = [
        make_item(source="NAVER_D2", url="https://example.com/1"),
        make_item(source="Toss_Tech", url="https://example.com/2"),
        make_item(source="Toss_Tech", url="https://example.com/3"),
    ]

    mock_response = MagicMock()
    mock_response.json.return_value = {"saved": 3, "skipped": 0}
    mock_response.raise_for_status.return_value = None

    with patch(
        "app.services.push_service.requests.post", return_value=mock_response
    ) as mock_post:
        result = service.push(items)

    sent_payload = mock_post.call_args.kwargs["json"]
    assert len(sent_payload) == 3
    assert result == {"saved": 3, "skipped": 0}
