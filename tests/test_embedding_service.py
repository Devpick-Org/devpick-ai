"""EmbeddingOrchestrator 단위 테스트 — 외부 의존성 mock 기반 (DP-218)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.schemas.summary import SummaryResponse
from app.services.embedding_service import EmbeddingOrchestrator

_VALID_SUMMARY = {
    "content_id": "cid-001",
    "level": "junior",
    "one_line_summary": "테스트 요약",
    "core_summary": [{"heading": "주제", "content": "내용"}],
    "key_points": ["포인트1"],
    "keywords": ["Python", "FastAPI"],
    "tags": ["백엔드"],
    "difficulty": "easy",
    "next_recommendation": "다음 학습",
    "study_questions": ["질문1"],
    "confidence": 0.9,
    "generated_at": "2026-03-18T00:00:00+00:00",
    "thumbnail_url": None,
}


@pytest.fixture()
def summary() -> SummaryResponse:
    return SummaryResponse.model_validate(_VALID_SUMMARY)


def _make_orchestrator() -> EmbeddingOrchestrator:
    """외부 의존성을 모두 mock한 EmbeddingOrchestrator 인스턴스를 생성한다."""
    with (
        patch("app.services.embedding_service.EmbeddingService"),
        patch("app.services.embedding_service.DocumentChunker"),
        patch("app.services.embedding_service.VectorStoreManager"),
        patch("app.services.embedding_service.VectorRepository"),
        patch("app.services.embedding_service.OpenAIEmbeddings"),
    ):
        orchestrator = EmbeddingOrchestrator(
            openai_api_key="test-key",
            mongo_uri="mongodb://localhost:27017",
            mongo_db="devpick",
        )
    return orchestrator


# ── embed_and_store ────────────────────────────────────────────────────────


def test_embed_and_store_calls_chunker(summary: SummaryResponse) -> None:
    orchestrator = _make_orchestrator()

    mock_doc = MagicMock()
    mock_doc.text = "청크 텍스트"
    orchestrator._chunker.chunk.return_value = [mock_doc]
    orchestrator._embedding_svc.embed.return_value = [[0.1, 0.2]]

    orchestrator.embed_and_store("cid-001", "원문 텍스트", summary)

    orchestrator._chunker.chunk.assert_called_once_with(
        content_id="cid-001",
        text="원문 텍스트",
        keywords=summary.keywords,
        tags=summary.tags,
    )


def test_embed_and_store_calls_embed_with_texts(summary: SummaryResponse) -> None:
    orchestrator = _make_orchestrator()

    mock_doc = MagicMock()
    mock_doc.text = "청크 텍스트"
    orchestrator._chunker.chunk.return_value = [mock_doc]
    orchestrator._embedding_svc.embed.return_value = [[0.1, 0.2]]

    orchestrator.embed_and_store("cid-001", "원문 텍스트", summary)

    orchestrator._embedding_svc.embed.assert_called_once_with(["청크 텍스트"])


def test_embed_and_store_saves_to_mongo(summary: SummaryResponse) -> None:
    orchestrator = _make_orchestrator()

    mock_doc = MagicMock()
    mock_doc.text = "청크 텍스트"
    mock_doc.metadata.content_id = "cid-001"
    mock_doc.metadata.chunk_index = 0
    mock_doc.metadata.keywords = ["Python"]
    mock_doc.metadata.tags = ["백엔드"]
    orchestrator._chunker.chunk.return_value = [mock_doc]
    orchestrator._embedding_svc.embed.return_value = [[0.1, 0.2]]

    orchestrator.embed_and_store("cid-001", "원문 텍스트", summary)

    orchestrator._vector_repo.save_chunks.assert_called_once()


def test_embed_and_store_adds_to_faiss(summary: SummaryResponse) -> None:
    orchestrator = _make_orchestrator()

    mock_doc = MagicMock()
    mock_doc.text = "청크 텍스트"
    mock_doc.metadata.content_id = "cid-001"
    mock_doc.metadata.chunk_index = 0
    mock_doc.metadata.keywords = []
    mock_doc.metadata.tags = []
    orchestrator._chunker.chunk.return_value = [mock_doc]
    orchestrator._embedding_svc.embed.return_value = [[0.1, 0.2]]

    orchestrator.embed_and_store("cid-001", "원문 텍스트", summary)

    orchestrator._vector_store.add_documents.assert_called_once()
    orchestrator._vector_store.save.assert_called_once()


def test_embed_and_store_skips_when_no_chunks(summary: SummaryResponse) -> None:
    """청킹 결과가 없으면 임베딩 및 저장을 건너뛴다."""
    orchestrator = _make_orchestrator()
    orchestrator._chunker.chunk.return_value = []

    orchestrator.embed_and_store("cid-001", "", summary)

    orchestrator._embedding_svc.embed.assert_not_called()
    orchestrator._vector_repo.save_chunks.assert_not_called()
    orchestrator._vector_store.add_documents.assert_not_called()
