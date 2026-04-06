"""EmbeddingOrchestrator 단위 테스트 — 외부 의존성 mock 기반 (DP-218)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.schemas.summary import AllLevelsSummaryResponse
from app.services.embedding_service import EmbeddingOrchestrator

_LEVEL_PAYLOAD = {
    "core_summary": [{"heading": "주제", "content": "내용"}],
    "key_points": ["포인트1"],
    "study_questions": ["질문1"],
    "next_recommendation": "다음 학습",
    "confidence": 0.9,
}

_VALID_ALL_LEVELS = {
    "content_id": "cid-001",
    "common": {
        "one_line_summary": "테스트 요약",
        "keywords": ["Python", "FastAPI"],
        "category": "Backend",
        "tags": ["백엔드"],
        "difficulty": "easy",
    },
    "beginner": _LEVEL_PAYLOAD,
    "junior": _LEVEL_PAYLOAD,
    "mid": _LEVEL_PAYLOAD,
    "senior": _LEVEL_PAYLOAD,
    "generated_at": "2026-03-18T00:00:00+00:00",
    "thumbnail_url": None,
}


def _make_orchestrator() -> EmbeddingOrchestrator:
    """외부 의존성을 모두 mock한 EmbeddingOrchestrator 인스턴스를 생성한다."""
    with (
        patch("app.services.embedding_service.EmbeddingService"),
        patch("app.services.embedding_service.DocumentChunker"),
        patch("app.services.embedding_service.VectorStoreManager"),
        patch("app.services.embedding_service.VectorRepository"),
        patch("boto3.client"),
    ):
        orchestrator = EmbeddingOrchestrator(aws_region="us-east-1")
    return orchestrator


# ── embed_and_store ────────────────────────────────────────────────────────


def test_embed_and_store_calls_chunker() -> None:
    orchestrator = _make_orchestrator()
    summary = AllLevelsSummaryResponse.model_validate(_VALID_ALL_LEVELS)

    mock_doc = MagicMock()
    mock_doc.text = "청크 텍스트"
    orchestrator._chunker.chunk.return_value = [mock_doc]
    orchestrator._embedding_svc.embed.return_value = [[0.1, 0.2]]

    orchestrator.embed_and_store("cid-001", "원문 텍스트", summary)

    orchestrator._chunker.chunk.assert_called_once_with(
        content_id="cid-001",
        text="원문 텍스트",
        keywords=summary.common.keywords,
        tags=summary.common.tags,
    )


def test_embed_and_store_calls_embed_with_texts() -> None:
    orchestrator = _make_orchestrator()
    summary = AllLevelsSummaryResponse.model_validate(_VALID_ALL_LEVELS)

    mock_doc = MagicMock()
    mock_doc.text = "청크 텍스트"
    orchestrator._chunker.chunk.return_value = [mock_doc]
    orchestrator._embedding_svc.embed.return_value = [[0.1, 0.2]]

    orchestrator.embed_and_store("cid-001", "원문 텍스트", summary)

    orchestrator._embedding_svc.embed.assert_called_once_with(["청크 텍스트"])


def test_embed_and_store_saves_to_mongo() -> None:
    orchestrator = _make_orchestrator()
    summary = AllLevelsSummaryResponse.model_validate(_VALID_ALL_LEVELS)

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


def test_embed_and_store_adds_to_faiss() -> None:
    orchestrator = _make_orchestrator()
    summary = AllLevelsSummaryResponse.model_validate(_VALID_ALL_LEVELS)

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


def test_embed_and_store_skips_when_no_chunks() -> None:
    """청킹 결과가 없으면 임베딩 및 저장을 건너뛴다."""
    orchestrator = _make_orchestrator()
    summary = AllLevelsSummaryResponse.model_validate(_VALID_ALL_LEVELS)
    orchestrator._chunker.chunk.return_value = []

    orchestrator.embed_and_store("cid-001", "", summary)

    orchestrator._embedding_svc.embed.assert_not_called()
    orchestrator._vector_repo.save_chunks.assert_not_called()
    orchestrator._vector_store.add_documents.assert_not_called()
