"""SummaryRepository 단위 테스트 — DynamoDB mock 기반, 실제 DB 호출 없음 (DP-300)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.repositories.summary_repository import SummaryRepository
from app.schemas.summary import AllLevelsSummaryResponse

_LEVEL_PAYLOAD = {
    "core_summary": "소제목\n요약 내용",
    "key_points": ["포인트1"],
    "additional_questions": ["질문1"],
    "next_recommendation": "다음 학습 주제",
    "confidence": 0.85,
}

_VALID_ALL_LEVELS = {
    "content_id": "test-all-001",
    "common": {
        "one_line_summary": "Redis TTL 설정 전략",
        "keywords": ["TTL", "캐시 무효화"],
        "category": "Backend",
        "tags": ["Redis", "백엔드"],
        "difficulty": "easy",
    },
    "beginner": _LEVEL_PAYLOAD,
    "junior": _LEVEL_PAYLOAD,
    "mid": _LEVEL_PAYLOAD,
    "senior": _LEVEL_PAYLOAD,
    "generated_at": "2026-03-23T00:00:00+00:00",
    "thumbnail_url": None,
}


@pytest.fixture()
def mock_table() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def repo(mock_table: MagicMock) -> SummaryRepository:
    with patch("boto3.resource") as mock_resource:
        mock_resource.return_value.Table.return_value = mock_table
        instance = SummaryRepository(aws_region="us-east-1")
    instance._table = mock_table
    return instance


# ─── DP-300: save_all_levels 테스트 ──────────────────────────────────────────


def test_save_all_levels_calls_update_item_4_times(
    repo: SummaryRepository, mock_table: MagicMock
) -> None:
    response = AllLevelsSummaryResponse.model_validate(_VALID_ALL_LEVELS)
    repo.save_all_levels("test-all-001", response)

    assert mock_table.update_item.call_count == 4


def test_save_all_levels_includes_all_level_names(
    repo: SummaryRepository, mock_table: MagicMock
) -> None:
    response = AllLevelsSummaryResponse.model_validate(_VALID_ALL_LEVELS)
    repo.save_all_levels("test-all-001", response)

    levels = {
        call.kwargs["Key"]["level"] for call in mock_table.update_item.call_args_list
    }
    assert levels == {"beginner", "junior", "mid", "senior"}


def test_save_all_levels_includes_common_fields(
    repo: SummaryRepository, mock_table: MagicMock
) -> None:
    response = AllLevelsSummaryResponse.model_validate(_VALID_ALL_LEVELS)
    repo.save_all_levels("test-all-001", response)

    for call in mock_table.update_item.call_args_list:
        expr_values = call.kwargs["ExpressionAttributeValues"]
        # one_line_summary は common フィールド
        assert any(v == "Redis TTL 설정 전략" for v in expr_values.values())
        assert any(v == "easy" for v in expr_values.values())


def test_save_all_levels_sets_content_id_key(
    repo: SummaryRepository, mock_table: MagicMock
) -> None:
    response = AllLevelsSummaryResponse.model_validate(_VALID_ALL_LEVELS)
    repo.save_all_levels("test-all-001", response)

    for call in mock_table.update_item.call_args_list:
        assert call.kwargs["Key"]["content_id"] == "test-all-001"


def test_save_all_levels_includes_created_at_if_not_exists(
    repo: SummaryRepository, mock_table: MagicMock
) -> None:
    response = AllLevelsSummaryResponse.model_validate(_VALID_ALL_LEVELS)
    repo.save_all_levels("test-all-001", response)

    for call in mock_table.update_item.call_args_list:
        expr = call.kwargs["UpdateExpression"]
        assert "if_not_exists(created_at" in expr
