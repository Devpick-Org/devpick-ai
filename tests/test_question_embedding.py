"""QuestionEmbeddingOrchestrator 단위 테스트 — mock 기반 (DP-234)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.question_embedding_service import QuestionEmbeddingOrchestrator


def _make_orchestrator() -> tuple[QuestionEmbeddingOrchestrator, MagicMock, MagicMock]:
    """mock 의존성을 주입한 QuestionEmbeddingOrchestrator를 반환한다."""
    mock_store = MagicMock()
    with (
        patch(
            "app.services.question_embedding_service.EmbeddingService"
        ) as mock_emb_cls,
        patch(
            "app.services.question_embedding_service.get_store", return_value=mock_store
        ),
        patch(
            "app.services.question_embedding_service.QuestionVectorRepository"
        ) as mock_repo_cls,
        patch("boto3.client"),
    ):
        mock_emb = MagicMock()
        mock_emb.embed.return_value = [[0.1] * 1024]
        mock_emb_cls.return_value = mock_emb

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        orch = QuestionEmbeddingOrchestrator(aws_region="us-east-1")
        orch._embedding_svc = mock_emb
        orch._vector_store = mock_store
        orch._question_repo = mock_repo

    return orch, mock_emb, mock_repo


def test_embed_and_store_calls_embedding() -> None:
    orch, mock_emb, _ = _make_orchestrator()

    orch.embed_and_store(
        question_id="q_001",
        text="useEffect 무한 렌더링\ndependency array를 비워두면",
    )

    mock_emb.embed.assert_called_once()
    text_arg = mock_emb.embed.call_args[0][0][0]
    assert "useEffect" in text_arg


def test_embed_and_store_saves_to_mongo() -> None:
    orch, mock_emb, mock_repo = _make_orchestrator()
    mock_emb.embed.return_value = [[0.5] * 1024]

    orch.embed_and_store(
        question_id="q_001",
        text="질문 텍스트",
        suggested_tags=["React", "useEffect"],
        content_id="article_001",
    )

    mock_repo.save_question.assert_called_once_with(
        question_id="q_001",
        text="질문 텍스트",
        embedding=[0.5] * 1024,
        suggested_tags=["React", "useEffect"],
        content_id="article_001",
    )


def test_embed_and_store_updates_faiss() -> None:
    orch, _, _ = _make_orchestrator()

    orch.embed_and_store(question_id="q_001", text="질문 텍스트")

    orch._vector_store.add_documents.assert_called_once()
    orch._vector_store.save.assert_called_once()


def test_embed_and_store_upserts_on_same_question_id() -> None:
    """같은 question_id로 두 번 호출하면 save_question이 두 번 호출된다 (upsert는 repo 레이어 책임)."""
    orch, mock_emb, mock_repo = _make_orchestrator()
    mock_emb.embed.return_value = [[0.1] * 1024]

    orch.embed_and_store(question_id="q_001", text="첫 번째 텍스트")
    orch.embed_and_store(question_id="q_001", text="두 번째 텍스트")

    assert mock_repo.save_question.call_count == 2


def test_embed_and_store_skips_empty_text() -> None:
    orch, mock_emb, mock_repo = _make_orchestrator()

    orch.embed_and_store(question_id="q_001", text="")

    mock_emb.embed.assert_not_called()
    mock_repo.save_question.assert_not_called()


def test_embed_and_store_skips_whitespace_text() -> None:
    orch, mock_emb, mock_repo = _make_orchestrator()

    orch.embed_and_store(question_id="q_001", text="   \n  ")

    mock_emb.embed.assert_not_called()
    mock_repo.save_question.assert_not_called()
