"""SummaryRepository 단위 테스트 — pymongo mock 기반, 실제 DB 호출 없음 (DP-220)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.repositories.summary_repository import SummaryRepository
from app.schemas.summary import SummaryResponse

_VALID_SUMMARY = {
    "content_id": "test-001",
    "level": "junior",
    "one_line_summary": "Redis TTL 설정 전략",
    "core_summary": [{"heading": "캐시 무효화", "content": "TTL로 자동 삭제된다."}],
    "key_points": ["TTL 설정"],
    "keywords": ["캐시 무효화", "TTL"],
    "tags": ["Redis"],
    "difficulty": "easy",
    "next_recommendation": "Pub/Sub 패턴도 학습해보세요.",
    "study_questions": ["TTL이란?"],
    "confidence": 0.9,
    "generated_at": "2026-03-16T00:00:00+00:00",
    "thumbnail_url": None,
}


@pytest.fixture()
def mock_collection() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def repo(mock_collection: MagicMock) -> SummaryRepository:
    with patch("app.repositories.summary_repository.MongoClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.__getitem__.return_value.__getitem__.return_value = mock_collection
        instance = SummaryRepository(
            mongo_uri="mongodb://localhost:27017", db_name="devpick"
        )
    instance._collection = mock_collection
    return instance


def test_save_calls_upsert_with_correct_filter(
    repo: SummaryRepository, mock_collection: MagicMock
) -> None:
    summary = SummaryResponse.model_validate(_VALID_SUMMARY)
    repo.save(summary)

    mock_collection.update_one.assert_called_once()
    call_args = mock_collection.update_one.call_args
    filter_doc = call_args[0][0]
    assert filter_doc == {"content_id": "test-001", "level": "junior"}


def test_save_includes_updated_at(
    repo: SummaryRepository, mock_collection: MagicMock
) -> None:
    summary = SummaryResponse.model_validate(_VALID_SUMMARY)
    repo.save(summary)

    call_args = mock_collection.update_one.call_args
    update_doc = call_args[0][1]
    assert "updated_at" in update_doc["$set"]


def test_save_includes_created_at_on_insert(
    repo: SummaryRepository, mock_collection: MagicMock
) -> None:
    summary = SummaryResponse.model_validate(_VALID_SUMMARY)
    repo.save(summary)

    call_args = mock_collection.update_one.call_args
    update_doc = call_args[0][1]
    assert "created_at" in update_doc["$setOnInsert"]


def test_save_upsert_true(repo: SummaryRepository, mock_collection: MagicMock) -> None:
    summary = SummaryResponse.model_validate(_VALID_SUMMARY)
    repo.save(summary)

    call_kwargs = mock_collection.update_one.call_args[1]
    assert call_kwargs.get("upsert") is True
