"""AllLevelsSummaryService 단위 테스트 — mock 기반, 실제 API 호출 없음 (DP-300)."""

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
from app.services.all_levels_summary_service import AllLevelsSummaryService

_LEVEL_PAYLOAD = {
    "core_summary": "개요\nRedis는 인메모리 키-값 저장소다.",
    "key_points": ["TTL로 자동 만료", "Write-Through 패턴"],
    "additional_questions": ["TTL이란 무엇인가?", "캐시 무효화 전략의 종류는?"],
    "next_recommendation": "Redis Pub/Sub 패턴도 학습해보세요.",
    "confidence": 0.88,
}

_VALID_LLM_PAYLOAD = {
    "common": {
        "one_line_summary": "Redis 캐시를 활용한 TTL 설정 전략",
        "keywords": ["캐시 무효화", "TTL", "EXPIRE"],
        "category": "Backend",
        "tags": ["Redis", "백엔드", "캐시"],
        "difficulty": "easy",
    },
    "beginner": _LEVEL_PAYLOAD,
    "junior": _LEVEL_PAYLOAD,
    "mid": _LEVEL_PAYLOAD,
    "senior": _LEVEL_PAYLOAD,
}


def _bedrock_response(payload: dict, tool_name: str = "save_all_summaries") -> dict:
    """Bedrock Converse API 응답 형식을 흉내 낸 dict을 반환한다."""
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


def _make_service_with_mock(payload: dict) -> tuple[AllLevelsSummaryService, MagicMock]:
    """mock boto3 클라이언트를 주입한 AllLevelsSummaryService를 반환한다."""
    with patch("boto3.client"):
        svc = AllLevelsSummaryService(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = _bedrock_response(payload)
    svc._client = mock_client
    return svc, mock_client


def test_summarize_all_success() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result = svc.summarize_all(
        content_id="art-001",
        text="Redis TTL에 대한 글입니다.",
        thumbnail_url="https://example.com/thumb.png",
    )

    assert result.content_id == "art-001"
    assert result.common.one_line_summary == "Redis 캐시를 활용한 TTL 설정 전략"
    assert result.common.difficulty == "easy"
    assert "Redis" in result.common.tags
    assert result.thumbnail_url == "https://example.com/thumb.png"


def test_summarize_all_four_levels_present() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result = svc.summarize_all(content_id="art-002", text="글 내용입니다.")

    assert result.beginner.confidence == pytest.approx(0.88)
    assert result.junior.confidence == pytest.approx(0.88)
    assert result.mid.confidence == pytest.approx(0.88)
    assert result.senior.confidence == pytest.approx(0.88)
    assert isinstance(result.beginner.core_summary, str)
    assert "개요" in result.beginner.core_summary


def test_summarize_all_generated_at_is_set() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result = svc.summarize_all(content_id="art-003", text="글 내용입니다.")

    assert result.generated_at  # ISO 8601 문자열 존재
    assert "T" in result.generated_at


def test_empty_text_raises() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    with pytest.raises(AIBadRequestError, match="요약할 텍스트가 없습니다"):
        svc.summarize_all(content_id="art-004", text="")


def test_no_tool_use_block_raises() -> None:
    with patch("boto3.client"):
        svc = AllLevelsSummaryService(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "텍스트 응답"}]}}
    }
    svc._client = mock_client

    with pytest.raises(AIInternalError, match="tool_use 블록이 없습니다"):
        svc.summarize_all(content_id="art-005", text="유효한 텍스트.")


def test_validation_error_raises_ai_internal_error() -> None:
    with patch("boto3.client"):
        svc = AllLevelsSummaryService(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = _bedrock_response(
        {"common": {"one_line_summary": "요약"}}  # 필수 필드 대부분 누락
    )
    svc._client = mock_client

    with pytest.raises(AIInternalError, match="파싱"):
        svc.summarize_all(content_id="art-006", text="텍스트.")


# ─── Bedrock 예외 → 커스텀 예외 변환 ─────────────────────────────────────────


def _make_service_with_api_error(side_effect: Exception) -> AllLevelsSummaryService:
    with patch("boto3.client"):
        svc = AllLevelsSummaryService(aws_region="us-east-1")
    mock_client = MagicMock()
    mock_client.converse.side_effect = side_effect
    svc._client = mock_client
    return svc


def test_api_timeout_raises_ai_timeout_error() -> None:
    svc = _make_service_with_api_error(ReadTimeoutError(endpoint_url="test"))

    with pytest.raises(AITimeoutError):
        svc.summarize_all(content_id="art-t1", text="텍스트.")


def test_rate_limit_raises_ai_upstream_error() -> None:
    svc = _make_service_with_api_error(
        ClientError(
            error_response={"Error": {"Code": "ThrottlingException", "Message": ""}},
            operation_name="Converse",
        )
    )

    with pytest.raises(AIUpstreamError):
        svc.summarize_all(content_id="art-t2", text="텍스트.")


def test_api_connection_error_raises_ai_upstream_error() -> None:
    svc = _make_service_with_api_error(EndpointConnectionError(endpoint_url="test"))

    with pytest.raises(AIUpstreamError):
        svc.summarize_all(content_id="art-t3", text="텍스트.")
