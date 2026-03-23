"""SimilarQuestionService 단위 테스트 — RAGRetriever mock 기반 (DP-235)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.rag.schemas import ChunkMetadata, RAGDocument
from app.schemas.similar_question import SimilarQuestion


def _make_doc(
    question_id: str, text: str, tags: list[str] | None = None
) -> RAGDocument:
    return RAGDocument(
        text=text,
        metadata=ChunkMetadata(
            content_id=question_id,
            chunk_index=0,
            keywords=[],
            tags=tags or [],
        ),
    )


@pytest.fixture()
def service():
    """SimilarQuestionService — RAGRetriever mock 처리."""
    from app.services.similar_question_service import SimilarQuestionService

    with patch("app.services.similar_question_service.RAGRetriever") as mock_cls:
        mock_retriever = MagicMock()
        mock_cls.return_value = mock_retriever
        svc = SimilarQuestionService(openai_api_key="test-key")
    svc._retriever = mock_retriever
    return svc


def test_search_returns_similar_questions(service) -> None:
    doc = _make_doc("q-001", "useEffect 무한 렌더링 문제", ["React"])
    service._retriever.search.return_value = [(doc, 0.85)]

    results = service.search("useEffect 렌더링")

    assert len(results) == 1
    assert isinstance(results[0], SimilarQuestion)
    assert results[0].question_id == "q-001"
    assert results[0].text == "useEffect 무한 렌더링 문제"
    assert results[0].score == pytest.approx(0.85)
    assert results[0].tags == ["React"]


def test_search_excludes_self(service) -> None:
    doc_self = _make_doc("q-001", "내 질문")
    doc_other = _make_doc("q-002", "다른 질문")
    service._retriever.search.return_value = [(doc_self, 0.99), (doc_other, 0.75)]

    results = service.search("내 질문", exclude_question_id="q-001")

    assert len(results) == 1
    assert results[0].question_id == "q-002"


def test_search_filters_below_threshold(service) -> None:
    doc_high = _make_doc("q-001", "유사 질문")
    doc_low = _make_doc("q-002", "무관한 질문")
    service._retriever.search.return_value = [(doc_high, 0.8), (doc_low, 0.1)]

    results = service.search("질문")

    assert len(results) == 1
    assert results[0].question_id == "q-001"


def test_search_respects_top_k(service) -> None:
    docs = [(_make_doc(f"q-{i}", f"질문 {i}"), 0.9 - i * 0.05) for i in range(10)]
    service._retriever.search.return_value = docs

    results = service.search("질문", top_k=3)

    assert len(results) == 3


def test_search_returns_empty_when_no_results(service) -> None:
    service._retriever.search.return_value = []

    results = service.search("아무 질문")

    assert results == []


def test_search_fetches_extra_when_excluding(service) -> None:
    service._retriever.search.return_value = []

    service.search("질문", top_k=5, exclude_question_id="q-001")

    service._retriever.search.assert_called_once_with("질문", top_k=10)


def test_search_no_extra_fetch_without_exclude(service) -> None:
    service._retriever.search.return_value = []

    service.search("질문", top_k=5)

    service._retriever.search.assert_called_once_with("질문", top_k=5)


def test_search_rounds_score(service) -> None:
    doc = _make_doc("q-001", "질문")
    service._retriever.search.return_value = [(doc, 0.876543210)]

    results = service.search("질문")

    assert results[0].score == 0.8765
