"""AnswerService 단위 테스트 — mock 기반, 실제 API 호출 없음 (DP-234)."""

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
from app.services.answer_service import AnswerService

_VALID_LLM_PAYLOAD = {
    "answer_content": "## useEffect 무한 렌더링 원인\n`dependency array`를 비워두면...",
    "key_points": [
        "dependency array 누락 시 매 렌더링마다 useEffect 실행",
        "빈 배열 `[]`은 마운트 시 1회만 실행",
    ],
    "suggested_tags": ["React", "useEffect", "렌더링"],
    "references": ["blog_001", "blog_002"],
    "confidence": 0.92,
}


def _make_service_with_mock(payload: dict) -> tuple[AnswerService, MagicMock]:
    """mock Bedrock 클라이언트를 주입한 AnswerService를 반환한다."""
    with patch("boto3.client"):
        svc = AnswerService(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tool-1",
                            "name": "save_answer",
                            "input": payload,
                        }
                    }
                ]
            }
        }
    }
    svc._client = mock_client
    return svc, mock_client


def test_answer_success() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result, references = svc.answer(
        refined_title="useEffect 무한 렌더링 원인",
        refined_content="dependency array를 비워두면 계속 렌더링됩니다",
    )

    assert result.answer_content == _VALID_LLM_PAYLOAD["answer_content"]
    assert result.key_points == _VALID_LLM_PAYLOAD["key_points"]
    assert result.suggested_tags == _VALID_LLM_PAYLOAD["suggested_tags"]
    assert result.related_contents == []  # 라우터에서 채움
    assert result.confidence == pytest.approx(0.92)
    assert result.generated_at  # ISO 8601 문자열이 비어있지 않음
    assert references == ["blog_001", "blog_002"]


def test_answer_with_article_chunks() -> None:
    svc, mock_client = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    svc.answer(
        refined_title="제목",
        refined_content="본문",
        article_chunks=["React 렌더링 사이클은...", "useEffect는..."],
    )

    call_kwargs = mock_client.converse.call_args[1]
    user_content = call_kwargs["messages"][0]["content"][0]["text"]
    assert "관련 아티클" in user_content
    assert "React 렌더링 사이클은" in user_content


def test_answer_without_article_chunks() -> None:
    svc, mock_client = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    svc.answer(refined_title="제목", refined_content="본문")

    call_kwargs = mock_client.converse.call_args[1]
    user_content = call_kwargs["messages"][0]["content"][0]["text"]
    assert "관련 아티클" not in user_content


def test_answer_with_rag_chunks() -> None:
    svc, mock_client = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    svc.answer(
        refined_title="제목",
        refined_content="본문",
        rag_chunks=["[출처: blog_001]\nReact useState 훅은..."],
    )

    call_kwargs = mock_client.converse.call_args[1]
    user_content = call_kwargs["messages"][0]["content"][0]["text"]
    assert "참고 문서" in user_content
    assert "blog_001" in user_content


def test_answer_with_original_question() -> None:
    svc, mock_client = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    svc.answer(
        refined_title="개선된 제목",
        refined_content="개선된 본문",
        original_title="원본 제목",
        original_content="뭔가 이상하게 렌더링됨",
    )

    call_kwargs = mock_client.converse.call_args[1]
    user_content = call_kwargs["messages"][0]["content"][0]["text"]
    assert "원본 질문" in user_content
    assert "뭔가 이상하게 렌더링됨" in user_content


def test_answer_with_suggested_tags() -> None:
    svc, mock_client = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    svc.answer(
        refined_title="제목",
        refined_content="본문",
        suggested_tags=["React", "useEffect"],
    )

    call_kwargs = mock_client.converse.call_args[1]
    user_content = call_kwargs["messages"][0]["content"][0]["text"]
    assert "관련 기술 태그" in user_content
    assert "React" in user_content


def test_answer_references_extracted() -> None:
    """LLM 응답에서 references가 올바르게 추출된다."""
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    _, references = svc.answer(refined_title="제목", refined_content="본문")

    assert references == ["blog_001", "blog_002"]


def test_answer_empty_references() -> None:
    """references가 빈 배열인 경우 빈 리스트가 반환된다."""
    payload = copy.deepcopy(_VALID_LLM_PAYLOAD)
    payload["references"] = []
    svc, _ = _make_service_with_mock(payload)

    _, references = svc.answer(refined_title="제목", refined_content="본문")

    assert references == []


def test_invalid_tool_response_raises() -> None:
    with patch("boto3.client"):
        svc = AnswerService(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "일반 텍스트 응답"}]}}
    }
    svc._client = mock_client

    with pytest.raises(AIInternalError, match="tool_use 블록이 없습니다"):
        svc.answer(refined_title="질문", refined_content="본문")


def test_empty_refined_title_raises() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    with pytest.raises(AIBadRequestError, match="개선된 질문 제목과 본문은 필수"):
        svc.answer(refined_title="", refined_content="본문")


def test_empty_refined_content_raises() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    with pytest.raises(AIBadRequestError, match="개선된 질문 제목과 본문은 필수"):
        svc.answer(refined_title="제목", refined_content="")


def test_missing_optional_fields_uses_fallback() -> None:
    """key_points/suggested_tags/confidence 누락 시 fallback 값으로 정상 반환."""
    with patch("boto3.client"):
        svc = AnswerService(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tool-1",
                            "name": "save_answer",
                            "input": {
                                "answer_content": "답변만"
                            },
                        }
                    }
                ]
            }
        }
    }
    svc._client = mock_client

    result, references = svc.answer(refined_title="질문", refined_content="본문")

    assert result.answer_content == "답변만"
    assert result.key_points == []
    assert result.suggested_tags == []
    assert result.confidence == 0.7
    assert references == []


# ─── SDK 예외 → 커스텀 예외 변환 단위 테스트 ───────────────────────


def _make_service_with_api_error(side_effect: Exception) -> AnswerService:
    with patch("boto3.client"):
        svc = AnswerService(aws_region="us-east-1")
    mock_client = MagicMock()
    mock_client.converse.side_effect = side_effect
    svc._client = mock_client
    return svc


def test_api_timeout_raises_ai_timeout_error() -> None:
    svc = _make_service_with_api_error(ReadTimeoutError(endpoint_url="test"))

    with pytest.raises(AITimeoutError):
        svc.answer(refined_title="질문", refined_content="본문")


def test_rate_limit_raises_ai_upstream_error() -> None:
    svc = _make_service_with_api_error(
        ClientError(
            error_response={"Error": {"Code": "ThrottlingException", "Message": ""}},
            operation_name="Converse",
        )
    )

    with pytest.raises(AIUpstreamError):
        svc.answer(refined_title="질문", refined_content="본문")


def test_api_connection_error_raises_ai_upstream_error() -> None:
    svc = _make_service_with_api_error(EndpointConnectionError(endpoint_url="test"))

    with pytest.raises(AIUpstreamError):
        svc.answer(refined_title="질문", refined_content="본문")
