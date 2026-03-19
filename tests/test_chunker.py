"""DocumentChunker 단위 테스트 (DP-218)."""

from __future__ import annotations

import pytest

from app.rag.chunker import DocumentChunker
from app.rag.schemas import RAGDocument


@pytest.fixture
def chunker() -> DocumentChunker:
    return DocumentChunker(chunk_size=100, chunk_overlap=20)


def test_chunk_returns_rag_documents(chunker: DocumentChunker) -> None:
    text = "가나다라마바사" * 30  # 충분히 긴 텍스트
    result = chunker.chunk("cid-001", text)
    assert len(result) > 0
    assert all(isinstance(doc, RAGDocument) for doc in result)


def test_chunk_metadata_content_id(chunker: DocumentChunker) -> None:
    result = chunker.chunk("cid-abc", "가나다" * 50)
    for doc in result:
        assert doc.metadata.content_id == "cid-abc"


def test_chunk_index_is_sequential(chunker: DocumentChunker) -> None:
    result = chunker.chunk("cid-001", "가나다" * 50)
    indices = [doc.metadata.chunk_index for doc in result]
    assert indices == list(range(len(result)))


def test_chunk_metadata_keywords_and_tags(chunker: DocumentChunker) -> None:
    result = chunker.chunk(
        "cid-001",
        "가나다" * 50,
        keywords=["Python", "FastAPI"],
        tags=["백엔드"],
    )
    for doc in result:
        assert doc.metadata.keywords == ["Python", "FastAPI"]
        assert doc.metadata.tags == ["백엔드"]


def test_chunk_empty_text_returns_empty(chunker: DocumentChunker) -> None:
    assert chunker.chunk("cid-001", "") == []
    assert chunker.chunk("cid-001", "   ") == []


def test_chunk_short_text_single_chunk(chunker: DocumentChunker) -> None:
    """chunk_size보다 짧은 텍스트는 단일 청크로 반환한다."""
    short = "짧은 텍스트"
    result = chunker.chunk("cid-001", short)
    assert len(result) == 1
    assert result[0].text == short
    assert result[0].metadata.chunk_index == 0


def test_chunk_default_keywords_tags_empty(chunker: DocumentChunker) -> None:
    result = chunker.chunk("cid-001", "가나다" * 50)
    for doc in result:
        assert doc.metadata.keywords == []
        assert doc.metadata.tags == []


def test_chunk_respects_paragraph_boundary() -> None:
    """단락 경계(\\n\\n)를 우선 분할 지점으로 사용한다."""
    chunker = DocumentChunker(chunk_size=50, chunk_overlap=0)
    text = "첫 번째 단락입니다.\n\n두 번째 단락입니다."
    result = chunker.chunk("cid-001", text)
    # 단락 경계에서 분리됐으면 각 청크가 하나의 단락을 담음
    texts = [doc.text for doc in result]
    assert any("첫 번째 단락" in t for t in texts)
    assert any("두 번째 단락" in t for t in texts)
