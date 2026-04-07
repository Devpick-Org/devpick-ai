"""VectorRepository 단위 테스트 — DynamoDB mock 기반, 실제 DB 호출 없음 (DP-218)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.repositories.vector_repository import VectorRepository, _embedding_to_dynamo

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
def mock_table() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def repo(mock_table: MagicMock) -> VectorRepository:
    with patch("boto3.resource") as mock_resource:
        mock_resource.return_value.Table.return_value = mock_table
        instance = VectorRepository(aws_region="us-east-1")
    instance._table = mock_table
    return instance


# ── save_chunks ────────────────────────────────────────────────────────────


def test_save_chunks_calls_update_item_once_per_chunk(
    repo: VectorRepository, mock_table: MagicMock
) -> None:
    repo.save_chunks(_CHUNKS)
    assert mock_table.update_item.call_count == len(_CHUNKS)


def test_save_chunks_uses_correct_key(
    repo: VectorRepository, mock_table: MagicMock
) -> None:
    repo.save_chunks(_CHUNKS)
    first_call = mock_table.update_item.call_args_list[0]
    key = first_call.kwargs["Key"]
    assert key == {"content_id": "cid-001", "chunk_index": 0}


def test_save_chunks_converts_embedding_to_decimal(
    repo: VectorRepository, mock_table: MagicMock
) -> None:
    repo.save_chunks(_CHUNKS)
    first_call = mock_table.update_item.call_args_list[0]
    expr_values = first_call.kwargs["ExpressionAttributeValues"]
    emb_val = expr_values[":embedding"]
    assert all(isinstance(v, Decimal) for v in emb_val)


def test_save_chunks_includes_updated_at(
    repo: VectorRepository, mock_table: MagicMock
) -> None:
    repo.save_chunks(_CHUNKS)
    first_call = mock_table.update_item.call_args_list[0]
    expr_values = first_call.kwargs["ExpressionAttributeValues"]
    assert ":updated_at" in expr_values


def test_save_chunks_includes_created_at_if_not_exists(
    repo: VectorRepository, mock_table: MagicMock
) -> None:
    repo.save_chunks(_CHUNKS)
    first_call = mock_table.update_item.call_args_list[0]
    expr = first_call.kwargs["UpdateExpression"]
    assert "if_not_exists(created_at" in expr


def test_save_chunks_noop_on_empty(
    repo: VectorRepository, mock_table: MagicMock
) -> None:
    repo.save_chunks([])
    mock_table.update_item.assert_not_called()


# ── find_by_content_id ──────────────────────────────────────────────────────


def test_find_by_content_id_queries_with_key_condition(
    repo: VectorRepository, mock_table: MagicMock
) -> None:
    mock_table.query.return_value = {"Items": []}
    repo.find_by_content_id("cid-001")
    mock_table.query.assert_called_once()


def test_find_by_content_id_returns_list(
    repo: VectorRepository, mock_table: MagicMock
) -> None:
    mock_table.query.return_value = {
        "Items": [
            {
                "content_id": "cid-001",
                "chunk_index": 0,
                "text": "청크",
                "embedding": [Decimal("0.1"), Decimal("0.2")],
            }
        ]
    }
    result = repo.find_by_content_id("cid-001")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["embedding"] == [0.1, 0.2]


# ── find_all ───────────────────────────────────────────────────────────────


def test_find_all_yields_dicts(
    repo: VectorRepository, mock_table: MagicMock
) -> None:
    dynamo_chunk = {
        "content_id": "cid-001",
        "chunk_index": 0,
        "text": "청크",
        "embedding": [Decimal("0.1"), Decimal("0.2")],
    }
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{"Items": [dynamo_chunk]}]
    mock_table.meta.client.get_paginator.return_value = mock_paginator

    result = list(repo.find_all())
    assert len(result) == 1
    assert result[0]["embedding"] == [0.1, 0.2]


# ── delete_by_content_id ───────────────────────────────────────────────────


def test_delete_by_content_id_queries_then_deletes(
    repo: VectorRepository, mock_table: MagicMock
) -> None:
    mock_table.query.return_value = {
        "Items": [
            {"content_id": "cid-001", "chunk_index": 0},
            {"content_id": "cid-001", "chunk_index": 1},
        ]
    }
    count = repo.delete_by_content_id("cid-001")
    assert mock_table.delete_item.call_count == 2
    assert count == 2


def test_delete_by_content_id_returns_zero_when_none(
    repo: VectorRepository, mock_table: MagicMock
) -> None:
    mock_table.query.return_value = {"Items": []}
    count = repo.delete_by_content_id("nonexistent")
    assert count == 0
    mock_table.delete_item.assert_not_called()


# ── helper ─────────────────────────────────────────────────────────────────


def test_embedding_to_dynamo_converts_floats() -> None:
    result = _embedding_to_dynamo([0.1, 0.2, 0.3])
    assert all(isinstance(v, Decimal) for v in result)
    assert result[0] == Decimal("0.1")
