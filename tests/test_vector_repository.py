"""VectorRepository 단위 테스트 — pymongo mock 기반, 실제 DB 호출 없음 (DP-218)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.repositories.vector_repository import VectorRepository

_CHUNKS = [
    {
        "content_id": "cid-001",
        "chunk_index": 0,
        "text": "첫 번째 청크",
        "embedding": [0.1, 0.2],
        "keywords": ["K1"],
        "tags": ["T1"],
    },
    {
        "content_id": "cid-001",
        "chunk_index": 1,
        "text": "두 번째 청크",
        "embedding": [0.3, 0.4],
        "keywords": ["K2"],
        "tags": ["T2"],
    },
]


@pytest.fixture()
def mock_collection() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def repo(mock_collection: MagicMock) -> VectorRepository:
    with patch("app.repositories.vector_repository.MongoClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.__getitem__.return_value.__getitem__.return_value = mock_collection
        instance = VectorRepository(
            mongo_uri="mongodb://localhost:27017", db_name="devpick"
        )
    instance._collection = mock_collection
    return instance


# ── save_chunks ────────────────────────────────────────────────────────────


def test_save_chunks_calls_update_once_per_chunk(
    repo: VectorRepository, mock_collection: MagicMock
) -> None:
    repo.save_chunks(_CHUNKS)
    assert mock_collection.update_one.call_count == len(_CHUNKS)


def test_save_chunks_uses_correct_filter(
    repo: VectorRepository, mock_collection: MagicMock
) -> None:
    repo.save_chunks(_CHUNKS)
    first_call = mock_collection.update_one.call_args_list[0]
    filter_doc = first_call[0][0]
    assert filter_doc == {"content_id": "cid-001", "chunk_index": 0}


def test_save_chunks_sets_updated_at(
    repo: VectorRepository, mock_collection: MagicMock
) -> None:
    repo.save_chunks(_CHUNKS)
    call_args = mock_collection.update_one.call_args_list[0]
    update_doc = call_args[0][1]
    assert "updated_at" in update_doc["$set"]


def test_save_chunks_sets_created_at_on_insert(
    repo: VectorRepository, mock_collection: MagicMock
) -> None:
    repo.save_chunks(_CHUNKS)
    call_args = mock_collection.update_one.call_args_list[0]
    update_doc = call_args[0][1]
    assert "created_at" in update_doc["$setOnInsert"]


def test_save_chunks_upsert_true(
    repo: VectorRepository, mock_collection: MagicMock
) -> None:
    repo.save_chunks(_CHUNKS)
    call_kwargs = mock_collection.update_one.call_args_list[0][1]
    assert call_kwargs.get("upsert") is True


def test_save_chunks_noop_on_empty(
    repo: VectorRepository, mock_collection: MagicMock
) -> None:
    repo.save_chunks([])
    mock_collection.update_one.assert_not_called()


# ── find_by_content_id ──────────────────────────────────────────────────────


def test_find_by_content_id_queries_correct_filter(
    repo: VectorRepository, mock_collection: MagicMock
) -> None:
    mock_collection.find.return_value.sort.return_value = iter(_CHUNKS)
    repo.find_by_content_id("cid-001")
    mock_collection.find.assert_called_once_with({"content_id": "cid-001"}, {"_id": 0})


def test_find_by_content_id_returns_list(
    repo: VectorRepository, mock_collection: MagicMock
) -> None:
    mock_collection.find.return_value.sort.return_value = iter(_CHUNKS)
    result = repo.find_by_content_id("cid-001")
    assert isinstance(result, list)


# ── find_all ───────────────────────────────────────────────────────────────


def test_find_all_yields_dicts(
    repo: VectorRepository, mock_collection: MagicMock
) -> None:
    mock_collection.find.return_value = iter(_CHUNKS)
    result = list(repo.find_all())
    assert result == _CHUNKS


# ── delete_by_content_id ───────────────────────────────────────────────────


def test_delete_by_content_id_calls_delete_many(
    repo: VectorRepository, mock_collection: MagicMock
) -> None:
    mock_collection.delete_many.return_value.deleted_count = 2
    count = repo.delete_by_content_id("cid-001")
    mock_collection.delete_many.assert_called_once_with({"content_id": "cid-001"})
    assert count == 2
