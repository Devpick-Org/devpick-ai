"""RefineService 단위 테스트 — mock 기반, 실제 API 호출 없음 (DP-231)."""

from __future__ import annotations

import copy
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from app.core.exceptions import (
    AIBadRequestError,
    AIInternalError,
    AITimeoutError,
    AIUpstreamError,
)
from app.services.refine_service import RefineService

_VALID_LLM_PAYLOAD = {
    "refined_title": "Redis TTL(Time To Live)을 설정하여 캐시 키 자동 만료를 구현하는 방법",
    "refined_content": (
        "Redis에서 TTL을 설정하여 캐시 키가 자동으로 만료되도록 하고 싶습니다.\n"
        "EXPIRE 명령과 SET EX 옵션의 차이, 그리고 TTL 설정 시 주의사항이 궁금합니다."
    ),
    "suggested_tags": ["Redis", "캐시", "TTL"],
    "confidence": 0.82,
}


def _bedrock_response(payload: dict, tool_name: str = "save_refined_question") -> dict:
    return {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tool-1",
                            "name": tool_name,
                            "input": payload,
                        }
                    }
                ]
            }
        }
    }


def _make_service_with_mock(payload: dict) -> tuple[RefineService, MagicMock]:
    """mock boto3 클라이언트를 주입한 RefineService를 반환한다."""
    with patch("boto3.client"):
        svc = RefineService(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = _bedrock_response(payload)
    svc._client = mock_client
    return svc, mock_client


def test_refine_success() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result = svc.refine(
        title="redis ttl",
        content="redis ttl이 뭔가요",
    )

    assert result.refined_title == _VALID_LLM_PAYLOAD["refined_title"]
    assert result.refined_content == _VALID_LLM_PAYLOAD["refined_content"]
    assert isinstance(result.suggested_tags, list)
    assert "Redis" in result.suggested_tags
    assert result.confidence == pytest.approx(0.82)
    assert result.generated_at  # ISO 8601 문자열이 비어있지 않음


def test_refine_with_context_chunks() -> None:
    svc, mock_client = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result = svc.refine(
        title="redis ttl",
        content="redis ttl이 뭔가요",
        context_chunks=["Redis EXPIRE 명령으로 키에 TTL을 설정한다."],
    )

    assert result.refined_title == _VALID_LLM_PAYLOAD["refined_title"]
    # Bedrock Converse API 호출 시 context_chunks가 user prompt에 포함되었는지 확인
    call_kwargs = mock_client.converse.call_args[1]
    user_content = call_kwargs["messages"][0]["content"][0]["text"]
    assert "참고 문서" in user_content
    assert "EXPIRE" in user_content


def test_refine_without_context_chunks() -> None:
    svc, mock_client = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    svc.refine(
        title="redis ttl",
        content="redis ttl이 뭔가요",
    )

    call_kwargs = mock_client.converse.call_args[1]
    user_content = call_kwargs["messages"][0]["content"][0]["text"]
    assert "참고 문서" not in user_content


def test_invalid_tool_response_raises() -> None:
    with patch("boto3.client"):
        svc = RefineService(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "텍스트 응답"}]}}
    }
    svc._client = mock_client

    with pytest.raises(AIInternalError, match="tool_use 블록이 없습니다"):
        svc.refine(title="질문", content="본문")


def test_empty_title_raises() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    with pytest.raises(AIBadRequestError, match="질문 제목과 본문은 필수"):
        svc.refine(title="", content="본문")


def test_empty_content_raises() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    with pytest.raises(AIBadRequestError, match="질문 제목과 본문은 필수"):
        svc.refine(title="제목", content="")


def test_validation_error_raises_ai_internal_error() -> None:
    """RefineResponse 파싱 실패 → AIInternalError."""
    with patch("boto3.client"):
        svc = RefineService(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = _bedrock_response(
        {"refined_title": "제목만"}  # 필수 필드 대부분 누락
    )
    svc._client = mock_client

    with pytest.raises(AIInternalError, match="파싱"):
        svc.refine(title="질문", content="본문")


# ─── Bedrock 예외 → 커스텀 예외 변환 ──────────────────────────────────────────


def _make_service_with_api_error(side_effect: Exception) -> RefineService:
    """converse가 지정된 예외를 raise하는 RefineService를 반환한다."""
    with patch("boto3.client"):
        svc = RefineService(aws_region="us-east-1")
    mock_client = MagicMock()
    mock_client.converse.side_effect = side_effect
    svc._client = mock_client
    return svc


def test_api_timeout_raises_ai_timeout_error() -> None:
    svc = _make_service_with_api_error(ReadTimeoutError(endpoint_url="test"))

    with pytest.raises(AITimeoutError):
        svc.refine(title="질문", content="본문")


def test_rate_limit_raises_ai_upstream_error() -> None:
    svc = _make_service_with_api_error(
        ClientError(
            error_response={"Error": {"Code": "ThrottlingException", "Message": ""}},
            operation_name="Converse",
        )
    )

    with pytest.raises(AIUpstreamError):
        svc.refine(title="질문", content="본문")


def test_api_connection_error_raises_ai_upstream_error() -> None:
    svc = _make_service_with_api_error(EndpointConnectionError(endpoint_url="test"))

    with pytest.raises(AIUpstreamError):
        svc.refine(title="질문", content="본문")
