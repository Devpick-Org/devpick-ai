"""Unit tests for StackOverflowCollector — mocks HTTP to test collection behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.collectors.stackoverflow import StackOverflowCollector, _build_body_candidate
from app.schemas.normalized_content import NormalizedContent


# ── Helpers ──────────────────────────────────────────────────────────────────


def make_question(
    question_id: int = 1,
    title: str = "How to use Spring Boot?",
    link: str = "https://stackoverflow.com/questions/1/how-to-use-spring-boot",
    body: str = "Detailed question body here.",
    tags: list[str] | None = None,
    is_answered: bool = True,
    creation_date: int = 1_700_000_000,
    owner_display_name: str = "devuser",
    score: int = 15,
    view_count: int = 1200,
) -> dict:
    return {
        "question_id": question_id,
        "title": title,
        "link": link,
        "body": body,
        "tags": tags if tags is not None else ["java", "spring-boot"],
        "is_answered": is_answered,
        "creation_date": creation_date,
        "owner": {"display_name": owner_display_name},
        "score": score,
        "view_count": view_count,
    }


def make_answer(
    question_id: int = 1,
    body: str = "Accepted answer body.",
    is_accepted: bool = True,
    score: int = 30,
) -> dict:
    return {
        "question_id": question_id,
        "body": body,
        "is_accepted": is_accepted,
        "score": score,
    }


def mock_get_response(json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


# ── fetch() — top-level pipeline ─────────────────────────────────────────────


def test_fetch_returns_normalized_contents() -> None:
    collector = StackOverflowCollector(min_score=5, min_views=500)
    question = make_question(score=15, view_count=1200)
    answer = make_answer()

    q_resp = mock_get_response({"items": [question], "quota_remaining": 290})
    a_resp = mock_get_response({"items": [answer]})

    with patch.object(collector.session, "get", side_effect=[q_resp, a_resp]):
        results = collector.fetch(tags=["java"])

    assert len(results) == 1
    content = results[0]
    assert isinstance(content, NormalizedContent)
    assert content.source_name == "Stack Overflow"
    assert content.title == "How to use Spring Boot?"
    assert content.canonical_url == "https://stackoverflow.com/questions/1/how-to-use-spring-boot"
    assert content.author == "devuser"
    assert content.is_original_visible is True
    assert content.license_type == "CC BY-SA 4.0"
    assert "java" in content.tags
    assert content.view_count == 1200
    assert content.likes == 15  # SO score → likes


def test_fetch_filters_out_low_view_count() -> None:
    """Questions with view_count < min_views must be filtered out."""
    collector = StackOverflowCollector(min_score=5, min_views=500)
    question = make_question(score=15, view_count=100)  # below min_views=500

    q_resp = mock_get_response({"items": [question], "quota_remaining": 290})

    with patch.object(collector.session, "get", return_value=q_resp):
        results = collector.fetch(tags=["java"])

    assert results == []


def test_fetch_keeps_question_with_exact_min_views() -> None:
    """view_count == min_views should pass the filter."""
    collector = StackOverflowCollector(min_score=5, min_views=500)
    question = make_question(score=10, view_count=500, is_answered=False)

    q_resp = mock_get_response({"items": [question], "quota_remaining": 290})

    with patch.object(collector.session, "get", return_value=q_resp):
        results = collector.fetch(tags=["java"])

    assert len(results) == 1


def test_fetch_returns_empty_on_empty_api_response() -> None:
    collector = StackOverflowCollector()
    q_resp = mock_get_response({"items": [], "quota_remaining": 290})

    with patch.object(collector.session, "get", return_value=q_resp):
        results = collector.fetch(tags=["java"])

    assert results == []


def test_fetch_returns_empty_on_exception() -> None:
    collector = StackOverflowCollector()

    with patch.object(
        collector.session, "get", side_effect=requests.ConnectionError("refused")
    ):
        results = collector.fetch(tags=["java"])

    assert results == []


def test_fetch_skips_question_without_link() -> None:
    collector = StackOverflowCollector(min_views=0)
    question = make_question()
    question.pop("link")
    question["is_answered"] = False

    q_resp = mock_get_response({"items": [question]})

    with patch.object(collector.session, "get", return_value=q_resp):
        results = collector.fetch(tags=["java"])

    assert results == []


def test_fetch_continues_when_answer_fetch_fails() -> None:
    collector = StackOverflowCollector(min_views=0)
    question = make_question(is_answered=True)

    q_resp = mock_get_response({"items": [question], "quota_remaining": 100})
    a_resp = MagicMock()
    a_resp.raise_for_status.side_effect = requests.HTTPError("500")

    with patch.object(collector.session, "get", side_effect=[q_resp, a_resp]):
        results = collector.fetch(tags=["java"])

    assert len(results) == 1
    assert results[0].canonical_url == question["link"]


# ── _fetch_questions — parameter checks ──────────────────────────────────────


def test_fetch_questions_uses_hot_sort() -> None:
    """sort parameter must be 'hot' (not 'votes')."""
    collector = StackOverflowCollector()
    q_resp = mock_get_response({"items": []})

    with patch.object(collector.session, "get", return_value=q_resp) as mock_get:
        collector._fetch_questions(tags=["python"])

    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["sort"] == "hot"


def test_fetch_questions_uses_default_days_back_7() -> None:
    """Default fromdate should be ~7 days ago."""
    from datetime import datetime, timezone, timedelta

    collector = StackOverflowCollector(days_back=7)
    q_resp = mock_get_response({"items": []})

    with patch.object(collector.session, "get", return_value=q_resp) as mock_get:
        collector._fetch_questions(tags=["python"])

    call_params = mock_get.call_args.kwargs["params"]
    expected_approx = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
    assert abs(call_params["fromdate"] - expected_approx) < 5  # within 5 seconds


def test_fetch_questions_sends_min_score() -> None:
    collector = StackOverflowCollector(min_score=5)
    q_resp = mock_get_response({"items": []})

    with patch.object(collector.session, "get", return_value=q_resp) as mock_get:
        collector._fetch_questions(tags=["python"])

    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["min"] == 5


def test_fetch_questions_includes_api_key_when_set() -> None:
    collector = StackOverflowCollector(api_key="mykey123")
    q_resp = mock_get_response({"items": []})

    with patch.object(collector.session, "get", return_value=q_resp) as mock_get:
        collector._fetch_questions(tags=["python"])

    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["key"] == "mykey123"


def test_fetch_questions_omits_api_key_when_not_set() -> None:
    collector = StackOverflowCollector(api_key=None)
    q_resp = mock_get_response({"items": []})

    with patch.object(collector.session, "get", return_value=q_resp) as mock_get:
        collector._fetch_questions(tags=["python"])

    call_params = mock_get.call_args.kwargs["params"]
    assert "key" not in call_params


def test_fetch_questions_joins_tags_with_semicolon() -> None:
    collector = StackOverflowCollector()
    q_resp = mock_get_response({"items": []})

    with patch.object(collector.session, "get", return_value=q_resp) as mock_get:
        collector._fetch_questions(tags=["java", "spring-boot"])

    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["tagged"] == "java;spring-boot"


def test_fetch_questions_omits_tagged_when_empty() -> None:
    collector = StackOverflowCollector()
    q_resp = mock_get_response({"items": []})

    with patch.object(collector.session, "get", return_value=q_resp) as mock_get:
        collector._fetch_questions(tags=[])

    call_params = mock_get.call_args.kwargs["params"]
    assert "tagged" not in call_params


# ── _fetch_answers_batch ──────────────────────────────────────────────────────


def test_fetch_answers_batch_groups_by_question_id() -> None:
    collector = StackOverflowCollector()
    a1 = make_answer(question_id=1, body="Answer 1", is_accepted=True)
    a2 = make_answer(question_id=2, body="Answer 2", is_accepted=False)
    a3 = make_answer(question_id=1, body="Top answer", is_accepted=False, score=10)

    a_resp = mock_get_response({"items": [a1, a2, a3]})

    with patch.object(collector.session, "get", return_value=a_resp):
        result = collector._fetch_answers_batch([1, 2])

    assert len(result[1]) == 2
    assert len(result[2]) == 1


def test_fetch_answers_batch_returns_empty_dict_on_error() -> None:
    collector = StackOverflowCollector()

    with patch.object(
        collector.session, "get", side_effect=requests.Timeout("timeout")
    ):
        result = collector._fetch_answers_batch([1, 2])

    assert result == {}


# ── _to_normalized_content ────────────────────────────────────────────────────


def test_to_normalized_content_includes_view_count_and_likes() -> None:
    collector = StackOverflowCollector()
    q = make_question(score=42, view_count=3000)

    result = collector._to_normalized_content(q, [])

    assert result is not None
    assert result.view_count == 3000
    assert result.likes == 42


def test_to_normalized_content_missing_link_returns_none() -> None:
    collector = StackOverflowCollector()
    q = make_question()
    q.pop("link")

    result = collector._to_normalized_content(q, [])

    assert result is None


def test_to_normalized_content_null_owner_uses_unknown() -> None:
    collector = StackOverflowCollector()
    q = make_question()
    q["owner"] = None

    result = collector._to_normalized_content(q, [])

    assert result is not None
    assert result.author == "Unknown"


def test_to_normalized_content_null_tags_uses_empty_list() -> None:
    collector = StackOverflowCollector()
    q = make_question()
    q["tags"] = None

    result = collector._to_normalized_content(q, [])

    assert result is not None
    assert result.tags == []


def test_to_normalized_content_preview_truncated_at_300_chars() -> None:
    collector = StackOverflowCollector()
    q = make_question(body="x" * 400)

    result = collector._to_normalized_content(q, [])

    assert result is not None
    assert result.preview is not None
    assert len(result.preview) == 303  # 300 + "..."
    assert result.preview.endswith("...")


def test_to_normalized_content_short_body_no_truncation() -> None:
    collector = StackOverflowCollector()
    q = make_question(body="Short body")

    result = collector._to_normalized_content(q, [])

    assert result is not None
    assert result.preview == "Short body"


def test_to_normalized_content_published_at_from_unix_timestamp() -> None:
    collector = StackOverflowCollector()
    q = make_question(creation_date=1_700_000_000)

    result = collector._to_normalized_content(q, [])

    assert result is not None
    assert result.published_at is not None
    assert "2023" in result.published_at


def test_to_normalized_content_body_candidate_includes_question_and_answers() -> None:
    collector = StackOverflowCollector()
    q = make_question(body="Question body")
    answers = [
        make_answer(body="Accepted answer", is_accepted=True, score=50),
        make_answer(body="Top answer", is_accepted=False, score=20),
    ]

    result = collector._to_normalized_content(q, answers)

    assert result is not None
    assert "## Question" in result.body_candidate
    assert "## Accepted Answer" in result.body_candidate
    assert "## Top Answers" in result.body_candidate


# ── _build_body_candidate ─────────────────────────────────────────────────────


def test_build_body_candidate_all_none_returns_none() -> None:
    assert _build_body_candidate(None, None, []) is None


def test_build_body_candidate_question_only() -> None:
    result = _build_body_candidate("Q body", None, [])
    assert result == "## Question\nQ body"


def test_build_body_candidate_with_accepted_answer() -> None:
    accepted = {"body": "Accepted body", "is_accepted": True}
    result = _build_body_candidate("Q body", accepted, [])
    assert "## Accepted Answer\nAccepted body" in result


def test_build_body_candidate_with_top_answers() -> None:
    top = [{"body": "Top 1"}, {"body": "Top 2"}]
    result = _build_body_candidate("Q body", None, top)
    assert "## Top Answers" in result
    assert "Top 1" in result
    assert "Top 2" in result


def test_build_body_candidate_answers_without_body_are_skipped() -> None:
    top = [{"body": None}, {"body": "Valid answer"}]
    result = _build_body_candidate(None, None, top)
    assert result is not None
    assert "Valid answer" in result
