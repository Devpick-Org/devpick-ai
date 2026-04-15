"""QuizService 단위 테스트 — mock 기반, 실제 API 호출 없음 (DP-265)."""

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
from app.services.quiz_service import QuizService

_LEVEL_PAYLOAD = {
    "estimated_minutes": 8,
    "questions": [
        {
            "type": "multiple_choice",
            "question": "Redis TTL이란 무엇인가?",
            "options": [
                {"id": "A", "text": "데이터 만료 시간"},
                {"id": "B", "text": "데이터 압축 방식"},
                {"id": "C", "text": "메모리 할당 단위"},
                {"id": "D", "text": "클러스터 노드 수"},
                {"id": "E", "text": "복제 지연 시간"},
            ],
            "correct_option_id": "A",
            "explanation": "TTL은 Time To Live로 데이터 자동 만료 시간을 설정한다.",
            "correct_answer": "",
        },
        {
            "type": "multiple_choice",
            "question": "EXPIRE 명령어의 역할은?",
            "options": [
                {"id": "A", "text": "키를 즉시 삭제"},
                {"id": "B", "text": "만료 시간 설정"},
                {"id": "C", "text": "키 이름 변경"},
                {"id": "D", "text": "값을 복사"},
                {"id": "E", "text": "클러스터 동기화"},
            ],
            "correct_option_id": "B",
            "explanation": "EXPIRE는 키에 만료 시간(초)을 설정하는 명령어다.",
            "correct_answer": "",
        },
        {
            "type": "short_answer",
            "question": "Redis에서 키 만료를 설정하는 명령어는?",
            "options": [],
            "correct_option_id": "",
            "explanation": "EXPIRE 명령어로 키의 TTL을 초 단위로 설정한다.",
            "correct_answer": "EXPIRE",
        },
    ],
}

_VALID_LLM_PAYLOAD = {
    "title": "Redis TTL 전략의 핵심",
    "beginner": _LEVEL_PAYLOAD,
    "junior": _LEVEL_PAYLOAD,
    "mid": _LEVEL_PAYLOAD,
    "senior": _LEVEL_PAYLOAD,
}


def _bedrock_response(payload: dict, tool_name: str = "save_quiz") -> dict:
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


def _make_service_with_mock(payload: dict) -> tuple[QuizService, MagicMock]:
    """mock boto3 클라이언트를 주입한 QuizService를 반환한다."""
    with patch("boto3.client"):
        svc = QuizService(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = _bedrock_response(payload)
    svc._client = mock_client
    return svc, mock_client


def test_generate_all_success() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result = svc.generate_all(content_id="art-001", text="Redis TTL에 대한 글입니다.")

    assert result.content_id == "art-001"
    assert result.title == "Redis TTL 전략의 핵심"
    assert result.quiz_id
    assert result.generated_at


def test_generate_all_four_levels_present() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result = svc.generate_all(content_id="art-002", text="글 내용입니다.")

    assert len(result.beginner.questions) == 3
    assert len(result.junior.questions) == 3
    assert len(result.mid.questions) == 3
    assert len(result.senior.questions) == 3


def test_generate_all_question_ids_injected() -> None:
    """question.id는 서비스에서 q1~q3으로 주입된다."""
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    result = svc.generate_all(content_id="art-003", text="글 내용입니다.")

    for level in (result.beginner, result.junior, result.mid, result.senior):
        ids = [q.id for q in level.questions]
        assert ids == ["q1", "q2", "q3"]


def test_generate_all_missing_level_triggers_retry() -> None:
    """누락된 레벨이 있으면 _retry_missing_levels를 호출한다."""
    with patch("boto3.client"):
        svc = QuizService(aws_region="us-east-1")

    mock_client = MagicMock()
    # 첫 번째 호출: senior 누락
    partial_payload = {k: v for k, v in _VALID_LLM_PAYLOAD.items() if k != "senior"}
    mock_client.converse.side_effect = [
        _bedrock_response(copy.deepcopy(partial_payload)),
        _bedrock_response({"senior": copy.deepcopy(_LEVEL_PAYLOAD)}),
    ]
    svc._client = mock_client

    result = svc.generate_all(content_id="art-004", text="글 내용입니다.")

    assert mock_client.converse.call_count == 2
    assert len(result.senior.questions) == 3


def test_generate_all_multiple_missing_levels_retry() -> None:
    """여러 레벨 누락 시 재시도 1회로 모두 채운다."""
    with patch("boto3.client"):
        svc = QuizService(aws_region="us-east-1")

    mock_client = MagicMock()
    partial_payload = {"title": "테스트", "beginner": copy.deepcopy(_LEVEL_PAYLOAD)}
    retry_payload = {
        "junior": copy.deepcopy(_LEVEL_PAYLOAD),
        "mid": copy.deepcopy(_LEVEL_PAYLOAD),
        "senior": copy.deepcopy(_LEVEL_PAYLOAD),
    }
    mock_client.converse.side_effect = [
        _bedrock_response(copy.deepcopy(partial_payload)),
        _bedrock_response(copy.deepcopy(retry_payload)),
    ]
    svc._client = mock_client

    result = svc.generate_all(content_id="art-005", text="글 내용입니다.")

    assert mock_client.converse.call_count == 2
    assert result.beginner
    assert result.junior
    assert result.mid
    assert result.senior


def test_empty_text_raises() -> None:
    svc, _ = _make_service_with_mock(copy.deepcopy(_VALID_LLM_PAYLOAD))

    with pytest.raises(AIBadRequestError):
        svc.generate_all(content_id="art-006", text="")


def test_no_tool_use_block_raises() -> None:
    with patch("boto3.client"):
        svc = QuizService(aws_region="us-east-1")

    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "텍스트 응답"}]}}
    }
    svc._client = mock_client

    with pytest.raises(AIInternalError, match="tool_use 블록이 없습니다"):
        svc.generate_all(content_id="art-007", text="유효한 텍스트.")


def test_validation_error_raises_ai_internal_error() -> None:
    """객관식 문제에 correct_answer가 있으면 Pydantic validation 실패 → AIInternalError."""
    with patch("boto3.client"):
        svc = QuizService(aws_region="us-east-1")

    bad_question = {
        "type": "multiple_choice",
        "question": "질문",
        "options": [{"id": c, "text": f"선지{c}"} for c in "ABCDE"],
        "correct_option_id": "A",
        "explanation": "해설",
        "correct_answer": "잘못된값",  # multiple_choice에 correct_answer 있으면 ValidationError
    }
    bad_level = {"estimated_minutes": 8, "questions": [bad_question] * 3}
    bad_payload = {
        "title": "제목",
        "beginner": bad_level,
        "junior": bad_level,
        "mid": bad_level,
        "senior": bad_level,
    }
    mock_client = MagicMock()
    mock_client.converse.return_value = _bedrock_response(bad_payload)
    svc._client = mock_client

    with pytest.raises(AIInternalError, match="파싱"):
        svc.generate_all(content_id="art-008", text="텍스트.")


def test_api_timeout_raises_ai_timeout_error() -> None:
    with patch("boto3.client"):
        svc = QuizService(aws_region="us-east-1")
    mock_client = MagicMock()
    mock_client.converse.side_effect = ReadTimeoutError(endpoint_url="test")
    svc._client = mock_client

    with pytest.raises(AITimeoutError):
        svc.generate_all(content_id="art-t1", text="텍스트.")


def test_rate_limit_raises_ai_upstream_error() -> None:
    with patch("boto3.client"):
        svc = QuizService(aws_region="us-east-1")
    mock_client = MagicMock()
    mock_client.converse.side_effect = ClientError(
        error_response={"Error": {"Code": "ThrottlingException", "Message": ""}},
        operation_name="Converse",
    )
    svc._client = mock_client

    with pytest.raises(AIUpstreamError):
        svc.generate_all(content_id="art-t2", text="텍스트.")


def test_api_connection_error_raises_ai_upstream_error() -> None:
    with patch("boto3.client"):
        svc = QuizService(aws_region="us-east-1")
    mock_client = MagicMock()
    mock_client.converse.side_effect = EndpointConnectionError(endpoint_url="test")
    svc._client = mock_client

    with pytest.raises(AIUpstreamError):
        svc.generate_all(content_id="art-t3", text="텍스트.")
