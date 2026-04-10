"""RAGRetriever 단위 테스트 — VectorStoreManager mock 기반 (DP-218)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.rag.retriever import RAGRetriever
from app.rag.schemas import ChunkMetadata, RAGDocument

_MOCK_DOC = RAGDocument(
    text="Redis TTL은 키가 자동으로 만료되는 시간입니다.",
    metadata=ChunkMetadata(
        content_id="cid-001",
        chunk_index=0,
        keywords=["Redis", "TTL"],
        tags=["캐시"],
    ),
)


@pytest.fixture()
def retriever() -> RAGRetriever:
    mock_store = MagicMock()
    with patch("app.rag.retriever.get_store", return_value=mock_store):
        instance = RAGRetriever(aws_region="us-east-1")
    return instance


def test_search_returns_results(retriever: RAGRetriever) -> None:
    retriever._store.search.return_value = [(_MOCK_DOC, 0.88)]
    results = retriever.search("Redis TTL이란?")
    assert len(results) == 1
    doc, score = results[0]
    assert isinstance(doc, RAGDocument)
    assert score == pytest.approx(0.88)


def test_search_passes_query_and_top_k(retriever: RAGRetriever) -> None:
    retriever._store.search.return_value = []
    retriever.search("질문", top_k=10)
    retriever._store.search.assert_called_once_with("질문", top_k=10)


def test_search_returns_empty_when_no_results(retriever: RAGRetriever) -> None:
    retriever._store.search.return_value = []
    result = retriever.search("없는 질문")
    assert result == []


def test_search_default_top_k_is_five(retriever: RAGRetriever) -> None:
    retriever._store.search.return_value = []
    retriever.search("질문")
    retriever._store.search.assert_called_once_with("질문", top_k=5)
