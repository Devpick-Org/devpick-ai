"""ContentPipeline 단위 테스트 — 서비스 mock 기반, 실제 AI/DB 호출 없음."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.content_pipeline import ContentPipeline


def _make_pipeline() -> tuple[ContentPipeline, dict[str, MagicMock]]:
    """ContentPipeline과 내부 서비스 mock dict를 반환한다."""
    mocks: dict[str, MagicMock] = {
        "preprocess": MagicMock(),
        "summary_svc": MagicMock(),
        "summary_repo": MagicMock(),
        "embedding": MagicMock(),
        "content_repo": MagicMock(),
    }

    with (
        patch(
            "app.services.content_pipeline.PreprocessService",
            return_value=mocks["preprocess"],
        ),
        patch(
            "app.services.content_pipeline.AllLevelsSummaryService",
            return_value=mocks["summary_svc"],
        ),
        patch(
            "app.services.content_pipeline.SummaryRepository",
            return_value=mocks["summary_repo"],
        ),
        patch(
            "app.services.content_pipeline.EmbeddingOrchestrator",
            return_value=mocks["embedding"],
        ),
    ):
        pipeline = ContentPipeline(aws_region="us-east-1")

    pipeline._preprocess = mocks["preprocess"]
    pipeline._summary_svc = mocks["summary_svc"]
    pipeline._summary_repo = mocks["summary_repo"]
    pipeline._embedding = mocks["embedding"]
    pipeline._content_repo = mocks["content_repo"]

    # 기본 반환값 설정
    mocks["preprocess"].preprocess.return_value = "정제된 텍스트"
    summary = MagicMock()
    summary.common.tags = ["Python", "Docker"]
    mocks["summary_svc"].summarize_all.return_value = summary

    return pipeline, mocks


# ── 전체 흐름 ─────────────────────────────────────────────────────────────────


def test_process_content_calls_all_four_steps() -> None:
    pipeline, mocks = _make_pipeline()

    pipeline.process_content(
        content_id="cid-001",
        body_html="<p>본문</p>",
        thumbnail_url="https://example.com/thumb.jpg",
    )

    mocks["preprocess"].preprocess.assert_called_once_with("<p>본문</p>")
    mocks["summary_svc"].summarize_all.assert_called_once()
    mocks["summary_repo"].save_all_levels.assert_called_once()
    mocks["embedding"].embed_and_store.assert_called_once()


def test_process_content_passes_content_id_to_summarize() -> None:
    pipeline, mocks = _make_pipeline()

    pipeline.process_content(content_id="cid-999", body_html="<p>본문</p>")

    call_kwargs = mocks["summary_svc"].summarize_all.call_args
    assert call_kwargs.kwargs["content_id"] == "cid-999"


def test_process_content_passes_preprocessed_text_to_summarize() -> None:
    pipeline, mocks = _make_pipeline()
    mocks["preprocess"].preprocess.return_value = "전처리된 텍스트"

    pipeline.process_content(content_id="cid-001", body_html="<p>원본</p>")

    call_kwargs = mocks["summary_svc"].summarize_all.call_args
    assert call_kwargs.kwargs["text"] == "전처리된 텍스트"


def test_process_content_passes_thumbnail_url_to_summarize() -> None:
    pipeline, mocks = _make_pipeline()

    pipeline.process_content(
        content_id="cid-001",
        body_html="<p>본문</p>",
        thumbnail_url="https://img.example.com/thumb.jpg",
    )

    call_kwargs = mocks["summary_svc"].summarize_all.call_args
    assert call_kwargs.kwargs["thumbnail_url"] == "https://img.example.com/thumb.jpg"


# ── body 없음 ─────────────────────────────────────────────────────────────────


def test_process_content_skips_when_body_is_none() -> None:
    pipeline, mocks = _make_pipeline()

    pipeline.process_content(content_id="cid-001", body_html=None)

    mocks["preprocess"].preprocess.assert_not_called()
    mocks["summary_svc"].summarize_all.assert_not_called()


def test_process_content_skips_when_body_is_empty_string() -> None:
    pipeline, mocks = _make_pipeline()

    pipeline.process_content(content_id="cid-001", body_html="")

    mocks["preprocess"].preprocess.assert_not_called()
    mocks["summary_svc"].summarize_all.assert_not_called()


# ── 단계별 실패 격리 ──────────────────────────────────────────────────────────


def test_preprocess_failure_stops_pipeline_without_propagating() -> None:
    pipeline, mocks = _make_pipeline()
    mocks["preprocess"].preprocess.side_effect = ValueError("파싱 실패")

    # 예외가 밖으로 나오지 않아야 함
    pipeline.process_content(content_id="cid-001", body_html="<p>본문</p>")

    mocks["summary_svc"].summarize_all.assert_not_called()


def test_summary_failure_does_not_propagate() -> None:
    pipeline, mocks = _make_pipeline()
    mocks["summary_svc"].summarize_all.side_effect = RuntimeError("Bedrock 에러")

    pipeline.process_content(content_id="cid-001", body_html="<p>본문</p>")

    mocks["summary_repo"].save_all_levels.assert_not_called()
    mocks["embedding"].embed_and_store.assert_not_called()


def test_dynamo_save_failure_does_not_stop_embedding() -> None:
    pipeline, mocks = _make_pipeline()
    mocks["summary_repo"].save_all_levels.side_effect = Exception("DynamoDB 에러")

    pipeline.process_content(content_id="cid-001", body_html="<p>본문</p>")

    # embedding은 여전히 호출돼야 함
    mocks["embedding"].embed_and_store.assert_called_once()


def test_embedding_failure_does_not_propagate() -> None:
    pipeline, mocks = _make_pipeline()
    mocks["embedding"].embed_and_store.side_effect = Exception("임베딩 실패")

    # 예외가 밖으로 나오지 않아야 함
    pipeline.process_content(content_id="cid-001", body_html="<p>본문</p>")


# ── content_tags 저장 ─────────────────────────────────────────────────────────


def test_save_content_tags_called_when_summary_has_tags() -> None:
    pipeline, mocks = _make_pipeline()

    pipeline.process_content(content_id="cid-001", body_html="<p>본문</p>")

    mocks["content_repo"].save_content_tags.assert_called_once_with(
        "cid-001", ["Python", "Docker"]
    )


def test_save_content_tags_not_called_when_tags_empty() -> None:
    pipeline, mocks = _make_pipeline()
    mocks["summary_svc"].summarize_all.return_value.common.tags = []

    pipeline.process_content(content_id="cid-001", body_html="<p>본문</p>")

    mocks["content_repo"].save_content_tags.assert_not_called()


def test_save_content_tags_not_called_without_content_repo() -> None:
    pipeline, mocks = _make_pipeline()
    pipeline._content_repo = None

    pipeline.process_content(content_id="cid-001", body_html="<p>본문</p>")

    mocks["content_repo"].save_content_tags.assert_not_called()


def test_save_content_tags_failure_does_not_propagate() -> None:
    pipeline, mocks = _make_pipeline()
    mocks["content_repo"].save_content_tags.side_effect = Exception("DB 오류")

    # 예외가 밖으로 나오지 않아야 함
    pipeline.process_content(content_id="cid-001", body_html="<p>본문</p>")

    # 이후 단계(임베딩)도 계속 실행돼야 함
    mocks["embedding"].embed_and_store.assert_called_once()
