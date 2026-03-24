"""이벤트 로그 저장 동작 테스트 (DP-252).

각 AI 엔드포인트에서 user_id 유무에 따라 EventRepository.save_event 호출 여부를 검증한다.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

_VALID_KEY = "test-internal-key"

# ── 공통 응답 fixture 데이터 ────────────────────────────────────────────────

_LEVEL_SUMMARY = {
    "core_summary": [{"heading": "개요", "content": "내용 요약."}],
    "key_points": ["포인트1"],
    "study_questions": ["질문1"],
    "next_recommendation": "다음 학습 주제",
    "confidence": 0.85,
}

_ALL_LEVELS_RESPONSE = {
    "content_id": "c-001",
    "common": {
        "one_line_summary": "Redis TTL 전략",
        "keywords": ["TTL"],
        "tags": ["Redis"],
        "difficulty": "easy",
    },
    "beginner": _LEVEL_SUMMARY,
    "junior": _LEVEL_SUMMARY,
    "mid": _LEVEL_SUMMARY,
    "senior": _LEVEL_SUMMARY,
    "generated_at": "2026-03-24T00:00:00+00:00",
    "thumbnail_url": None,
}

_SUMMARY_RESPONSE = {
    "content_id": "c-001",
    "level": "junior",
    "one_line_summary": "Redis TTL 전략",
    "core_summary": [{"heading": "개요", "content": "내용 요약."}],
    "key_points": ["포인트1"],
    "keywords": ["TTL"],
    "tags": ["Redis"],
    "difficulty": "easy",
    "next_recommendation": "다음",
    "study_questions": ["질문1"],
    "confidence": 0.9,
    "generated_at": "2026-03-24T00:00:00+00:00",
    "thumbnail_url": None,
}


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def patch_internal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.deps._INTERNAL_KEY", _VALID_KEY)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def mock_all_levels_service():
    from app.schemas.summary import AllLevelsSummaryResponse

    mock_result = AllLevelsSummaryResponse.model_validate(_ALL_LEVELS_RESPONSE)
    with patch("app.api.internal.router.AllLevelsSummaryService") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.summarize_all.return_value = mock_result
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def mock_summary_service():
    from app.schemas.summary import SummaryResponse

    mock_result = SummaryResponse.model_validate(_SUMMARY_RESPONSE)
    with patch("app.api.internal.router.SummaryService") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.summarize.return_value = mock_result
        mock_cls.return_value = mock_instance
        yield mock_instance


# ── POST /internal/summaries 이벤트 로그 테스트 ────────────────────────────


def test_summaries_event_saved_when_user_id_provided(
    client: TestClient,
    mock_all_levels_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """user_id가 있으면 ALL_LEVELS_SUMMARY_GENERATED 이벤트가 저장된다."""
    monkeypatch.setattr(
        "app.api.internal.router._MONGO_URI", "mongodb://localhost:27017"
    )

    with patch("app.api.internal.router.EventRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/summaries",
            json={"content_id": "c-001", "text": "<p>본문</p>", "user_id": "u-001"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo.save_event.assert_called_once()
    call_kwargs = mock_repo.save_event.call_args.kwargs
    assert call_kwargs["user_id"] == "u-001"
    assert call_kwargs["event_type"].value == "ALL_LEVELS_SUMMARY_GENERATED"
    assert call_kwargs["content_id"] == "c-001"


def test_summaries_event_skipped_when_no_user_id(
    client: TestClient,
    mock_all_levels_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """user_id가 없으면 EventRepository를 호출하지 않는다."""
    monkeypatch.setattr(
        "app.api.internal.router._MONGO_URI", "mongodb://localhost:27017"
    )

    with patch("app.api.internal.router.EventRepository") as mock_repo_cls:
        resp = client.post(
            "/internal/summaries",
            json={"content_id": "c-001", "text": "<p>본문</p>"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo_cls.assert_not_called()


def test_summaries_event_skipped_when_mongo_uri_empty(
    client: TestClient,
    mock_all_levels_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MONGO_URI가 비어 있으면 EventRepository를 호출하지 않는다."""
    monkeypatch.setattr("app.api.internal.router._MONGO_URI", "")

    with patch("app.api.internal.router.EventRepository") as mock_repo_cls:
        resp = client.post(
            "/internal/summaries",
            json={"content_id": "c-001", "text": "<p>본문</p>", "user_id": "u-001"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo_cls.assert_not_called()


def test_summaries_event_failure_does_not_affect_response(
    client: TestClient,
    mock_all_levels_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이벤트 저장 실패해도 메인 응답은 200을 반환한다."""
    monkeypatch.setattr(
        "app.api.internal.router._MONGO_URI", "mongodb://localhost:27017"
    )

    with patch("app.api.internal.router.EventRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.save_event.side_effect = Exception("MongoDB 연결 실패")
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/summaries",
            json={"content_id": "c-001", "text": "<p>본문</p>", "user_id": "u-001"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    assert resp.json()["content_id"] == "c-001"


# ── POST /internal/summary 이벤트 로그 테스트 ─────────────────────────────


def test_summary_event_saved_with_level_metadata(
    client: TestClient,
    mock_summary_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """요약 레벨이 metadata로 함께 저장된다."""
    monkeypatch.setattr(
        "app.api.internal.router._MONGO_URI", "mongodb://localhost:27017"
    )

    with patch("app.api.internal.router.EventRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo

        resp = client.post(
            "/internal/summary",
            json={
                "content_id": "c-001",
                "level": "junior",
                "text": "<p>본문</p>",
                "user_id": "u-001",
            },
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    call_kwargs = mock_repo.save_event.call_args.kwargs
    assert call_kwargs["event_type"].value == "SUMMARY_GENERATED"
    assert call_kwargs["metadata"] == {"level": "junior"}


def test_summary_event_skipped_when_no_user_id(
    client: TestClient,
    mock_summary_service: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """user_id 없으면 이벤트 로그를 저장하지 않는다."""
    monkeypatch.setattr(
        "app.api.internal.router._MONGO_URI", "mongodb://localhost:27017"
    )

    with patch("app.api.internal.router.EventRepository") as mock_repo_cls:
        resp = client.post(
            "/internal/summary",
            json={"content_id": "c-001", "level": "junior", "text": "<p>본문</p>"},
            headers={"X-Internal-Key": _VALID_KEY},
        )

    assert resp.status_code == 200
    mock_repo_cls.assert_not_called()
