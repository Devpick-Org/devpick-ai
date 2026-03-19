"""VectorStoreManager 단위 테스트 — FAISS mock 기반, 실제 파일 I/O 없음 (DP-218)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.rag.schemas import ChunkMetadata, RAGDocument
from app.rag.vector_store import VectorStoreManager

_DOCS = [
    RAGDocument(
        text="첫 번째 청크",
        metadata=ChunkMetadata(
            content_id="cid-001", chunk_index=0, keywords=["K1"], tags=["T1"]
        ),
    ),
    RAGDocument(
        text="두 번째 청크",
        metadata=ChunkMetadata(
            content_id="cid-001", chunk_index=1, keywords=["K2"], tags=["T2"]
        ),
    ),
]


@pytest.fixture()
def mock_embedding_model() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def manager(mock_embedding_model: MagicMock) -> VectorStoreManager:
    mgr = VectorStoreManager(
        embedding_model=mock_embedding_model, index_path="data/vectors/test"
    )
    return mgr


# ── load_or_create ─────────────────────────────────────────────────────────


def test_load_or_create_loads_when_file_exists(manager: VectorStoreManager) -> None:
    with (
        patch("app.rag.vector_store.os.path.exists", return_value=True),
        patch("app.rag.vector_store.FAISS.load_local") as mock_load,
    ):
        mock_load.return_value = MagicMock()
        manager.load_or_create()
        mock_load.assert_called_once()
        assert manager._store is not None


def test_load_or_create_sets_none_when_no_file(manager: VectorStoreManager) -> None:
    with patch("app.rag.vector_store.os.path.exists", return_value=False):
        manager.load_or_create()
        assert manager._store is None


# ── add_documents ──────────────────────────────────────────────────────────


def test_add_documents_creates_store_when_none(manager: VectorStoreManager) -> None:
    """store가 None일 때 FAISS.from_texts로 인덱스를 생성한다."""
    with patch("app.rag.vector_store.FAISS.from_texts") as mock_from:
        mock_from.return_value = MagicMock()
        manager._store = None
        manager.add_documents(_DOCS)
        mock_from.assert_called_once()


def test_add_documents_appends_when_store_exists(manager: VectorStoreManager) -> None:
    """store가 있을 때 add_texts로 추가한다."""
    mock_store = MagicMock()
    manager._store = mock_store
    manager.add_documents(_DOCS)
    mock_store.add_texts.assert_called_once()


def test_add_documents_noop_on_empty_list(manager: VectorStoreManager) -> None:
    mock_store = MagicMock()
    manager._store = mock_store
    manager.add_documents([])
    mock_store.add_texts.assert_not_called()


def test_add_documents_passes_texts_and_metadatas(manager: VectorStoreManager) -> None:
    with patch("app.rag.vector_store.FAISS.from_texts") as mock_from:
        mock_from.return_value = MagicMock()
        manager._store = None
        manager.add_documents(_DOCS)
        _, kwargs = mock_from.call_args
        texts = kwargs.get("texts") or mock_from.call_args[0][0]
        assert "첫 번째 청크" in texts


# ── search ─────────────────────────────────────────────────────────────────


def test_search_returns_empty_when_store_none(manager: VectorStoreManager) -> None:
    manager._store = None
    result = manager.search("쿼리")
    assert result == []


def test_search_returns_rag_documents(manager: VectorStoreManager) -> None:
    from langchain_core.documents import Document

    lc_doc = Document(
        page_content="청크 텍스트",
        metadata={
            "content_id": "cid-001",
            "chunk_index": 0,
            "keywords": [],
            "tags": [],
        },
    )
    mock_store = MagicMock()
    mock_store.similarity_search_with_relevance_scores.return_value = [(lc_doc, 0.9)]
    manager._store = mock_store

    results = manager.search("쿼리", top_k=3)
    assert len(results) == 1
    doc, score = results[0]
    assert isinstance(doc, RAGDocument)
    assert score == pytest.approx(0.9)


def test_search_passes_top_k(manager: VectorStoreManager) -> None:
    mock_store = MagicMock()
    mock_store.similarity_search_with_relevance_scores.return_value = []
    manager._store = mock_store
    manager.search("쿼리", top_k=7)
    mock_store.similarity_search_with_relevance_scores.assert_called_once_with(
        "쿼리", k=7
    )


# ── save ───────────────────────────────────────────────────────────────────


def test_save_noop_when_store_none(manager: VectorStoreManager) -> None:
    """store가 없으면 save_local을 호출하지 않는다."""
    manager._store = None
    with patch("app.rag.vector_store.os.makedirs") as mock_mkdir:
        manager.save()
        mock_mkdir.assert_not_called()


def test_save_calls_save_local(manager: VectorStoreManager) -> None:
    mock_store = MagicMock()
    manager._store = mock_store
    with (
        patch("app.rag.vector_store.os.makedirs"),
        patch(
            "app.rag.vector_store.os.path.split", return_value=("data/vectors", "test")
        ),
    ):
        manager.save()
        mock_store.save_local.assert_called_once()
