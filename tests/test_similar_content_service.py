"""SimilarContentService 단위 테스트 — RAGRetriever mock 기반 (DP-288)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.rag.schemas import ChunkMetadata, RAGDocument
from app.schemas.similar_content import SimilarContent


def _make_doc(content_id: str, text: str = "본문") -> RAGDocument:
    return RAGDocument(
        text=text,
        metadata=ChunkMetadata(
            content_id=content_id,
            chunk_index=0,
            keywords=[],
            tags=[],
        ),
    )


@pytest.fixture()
def service():
    """SimilarContentService — RAGRetriever mock 처리."""
    from app.services.similar_content_service import SimilarContentService

    with patch("app.services.similar_content_service.RAGRetriever") as mock_cls:
        mock_retriever = MagicMock()
        mock_cls.return_value = mock_retriever
        svc = SimilarContentService(aws_region="us-east-1")
    svc._retriever = mock_retriever
    return svc


def test_search_returns_similar_contents(service) -> None:
    doc = _make_doc("article-001")
    service._retriever.search.return_value = [(doc, 0.85)]

    results = service.search("React 상태 관리")

    assert len(results) == 1
    assert isinstance(results[0], SimilarContent)
    assert results[0].content_id == "article-001"
    assert results[0].score == pytest.approx(0.85)


def test_search_aggregates_chunks_by_max_score(service) -> None:
    """같은 content_id의 여러 청크 중 MAX 점수를 사용한다."""
    doc1 = _make_doc("article-001")
    doc2 = _make_doc("article-001")
    doc3 = _make_doc("article-002")
    service._retriever.search.return_value = [
        (doc1, 0.60),
        (doc2, 0.90),  # article-001의 MAX
        (doc3, 0.75),
    ]

    results = service.search("쿼리")

    assert len(results) == 2
    article_001 = next(r for r in results if r.content_id == "article-001")
    assert article_001.score == pytest.approx(0.90)


def test_search_excludes_self(service) -> None:
    doc_self = _make_doc("article-self")
    doc_other = _make_doc("article-other")
    service._retriever.search.return_value = [
        (doc_self, 0.99),
        (doc_other, 0.75),
    ]

    results = service.search("쿼리", exclude_content_id="article-self")

    assert len(results) == 1
    assert results[0].content_id == "article-other"


def test_search_excludes_self_even_if_highest_score(service) -> None:
    doc_self = _make_doc("article-self")
    service._retriever.search.return_value = [(doc_self, 0.99)]

    results = service.search("쿼리", exclude_content_id="article-self")

    assert results == []


def test_search_filters_below_threshold(service) -> None:
    doc_high = _make_doc("article-001")
    doc_low = _make_doc("article-002")
    service._retriever.search.return_value = [(doc_high, 0.8), (doc_low, 0.1)]

    results = service.search("쿼리")

    assert len(results) == 1
    assert results[0].content_id == "article-001"


def test_search_respects_top_k(service) -> None:
    docs = [(_make_doc(f"article-{i}"), 0.9 - i * 0.05) for i in range(10)]
    service._retriever.search.return_value = docs

    results = service.search("쿼리", top_k=3)

    assert len(results) == 3


def test_search_sorts_by_score_descending(service) -> None:
    docs = [
        (_make_doc("article-a"), 0.75),
        (_make_doc("article-b"), 0.9),
        (_make_doc("article-c"), 0.8),
    ]
    service._retriever.search.return_value = docs

    results = service.search("쿼리")

    assert [r.content_id for r in results] == ["article-b", "article-c", "article-a"]


def test_search_returns_empty_when_no_results(service) -> None:
    service._retriever.search.return_value = []

    results = service.search("쿼리")

    assert results == []


def test_search_always_fetches_cap(service) -> None:
    """threshold 주도 방식 — top_k 무관하게 항상 _FETCH_CAP(100)개 fetch."""
    service._retriever.search.return_value = []

    service.search("쿼리", top_k=5)

    service._retriever.search.assert_called_once_with("쿼리", top_k=100)


def test_search_rounds_score(service) -> None:
    doc = _make_doc("article-001")
    service._retriever.search.return_value = [(doc, 0.876543210)]

    results = service.search("쿼리")

    assert results[0].score == 0.8765
