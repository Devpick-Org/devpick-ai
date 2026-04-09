"""Unit tests for StackOverflowCollector — mocks HTTP to test hybrid crawl+API behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from app.collectors.stackoverflow import StackOverflowCollector, _build_body_candidate
from app.schemas.normalized_content import NormalizedContent

# ── HTML 픽스처 ─────────────────────────────────────────────────────────────

# 실제 SO trending 페이지 HTML 구조를 최대한 반영한 픽스처
_TRENDING_HTML = (
    '<html><body>'
    '<div class="s-post-summary js-post-summary" data-post-id="12345" data-post-type-id="1" itemprop="item" itemscope>'
    '<div class="s-post-summary--stats js-post-summary-stats">'
    '<div class="s-post-summary--stats-item s-post-summary--stats-item__emphasized" title="Score of 15">'
    '<span class="s-post-summary--stats-item-number" itemprop="upvoteCount">15</span>'
    '<span class="s-post-summary--stats-item-unit">votes</span>'
    '</div>'
    '<div class="s-post-summary--stats-item" title="1,200 views">'
    '<span class="s-post-summary--stats-item-number">1,200</span>'
    '<span class="s-post-summary--stats-item-unit">views</span>'
    '</div>'
    '<meta itemprop="dateCreated" content="2026-03-15T10:00:00Z" />'
    '</div>'
    '<div class="s-post-summary--content">'
    '<h3 class="s-post-summary--content-title">'
    '<a href="/questions/12345/how-to-use-spring-boot" class="s-link" itemprop="url">'
    '<span itemprop="name">How to use Spring Boot?</span></a>'
    '</h3>'
    '<div class="s-post-summary--content-excerpt" itemprop="text">This is a preview of the question body.</div>'
    '<div class="s-post-summary--meta">'
    '<a href="/users/9999/devuser" class="s-avatar s-avatar__16" data-user-id="9999"></a>'
    '</div>'
    '</div>'
    '</div>'
    '</body></html>'
)

_API_QUESTION = {
    "question_id": 12345,
    "title": "How to use Spring Boot?",
    "link": "https://stackoverflow.com/questions/12345/how-to-use-spring-boot",
    "body": "<p>Detailed question body</p>",
    "tags": ["java", "spring-boot"],
    "is_answered": True,
    "creation_date": 1_700_000_000,
    "owner": {"display_name": "devuser"},
    "score": 15,
    "view_count": 1200,
}

_API_ANSWER = {
    "question_id": 12345,
    "body": "<p>Accepted answer body.</p>",
    "is_accepted": True,
    "score": 30,
}


def mock_response(json_data: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.raise_for_status.return_value = None
    return resp


# ── fetch() — 전체 파이프라인 ─────────────────────────────────────────────────


def test_fetch_returns_normalized_contents() -> None:
    collector = StackOverflowCollector()

    html_resp = mock_response(text=_TRENDING_HTML)
    body_resp = mock_response(
        json_data={"items": [_API_QUESTION], "quota_remaining": 290}
    )
    ans_resp = mock_response(json_data={"items": [_API_ANSWER]})

    with patch.object(collector.session, "get", side_effect=[html_resp, body_resp, ans_resp]):
        results = collector.fetch()

    assert len(results) == 1
    content = results[0]
    assert isinstance(content, NormalizedContent)
    assert content.source_name == "Stack Overflow"
    assert content.title == "How to use Spring Boot?"
    assert content.canonical_url == "https://stackoverflow.com/questions/12345/how-to-use-spring-boot"
    assert content.is_original_visible is True
    assert content.license_type == "CC BY-SA 4.0"
    assert content.view_count == 1200
    assert content.likes == 15


def test_fetch_returns_empty_when_trending_page_empty() -> None:
    collector = StackOverflowCollector()
    html_resp = mock_response(text="<html><body></body></html>")

    with patch.object(collector.session, "get", return_value=html_resp):
        results = collector.fetch()

    assert results == []


def test_fetch_returns_empty_on_connection_error() -> None:
    collector = StackOverflowCollector()

    with patch.object(
        collector.session, "get", side_effect=requests.ConnectionError("refused")
    ):
        results = collector.fetch()

    assert results == []


def test_fetch_continues_when_body_api_fails() -> None:
    """body API 실패해도 HTML 메타데이터로 NormalizedContent 생성."""
    collector = StackOverflowCollector()

    html_resp = mock_response(text=_TRENDING_HTML)
    body_resp = MagicMock()
    body_resp.raise_for_status.side_effect = requests.HTTPError("500")

    with patch.object(collector.session, "get", side_effect=[html_resp, body_resp]):
        results = collector.fetch()

    # body 없이도 canonical_url이 있으면 결과 생성
    assert len(results) == 1
    assert results[0].body_candidate is None


def test_fetch_continues_when_answer_api_fails() -> None:
    """answer API 실패해도 question만으로 결과 생성."""
    collector = StackOverflowCollector()

    html_resp = mock_response(text=_TRENDING_HTML)
    body_resp = mock_response(
        json_data={"items": [_API_QUESTION], "quota_remaining": 100}
    )
    ans_resp = MagicMock()
    ans_resp.raise_for_status.side_effect = requests.HTTPError("500")

    with patch.object(collector.session, "get", side_effect=[html_resp, body_resp, ans_resp]):
        results = collector.fetch()

    assert len(results) == 1
    assert results[0].accepted_answer is None
    assert results[0].top_answers == []


# ── _scrape_trending_page ────────────────────────────────────────────────────


def test_scrape_trending_page_extracts_post_id() -> None:
    collector = StackOverflowCollector()
    html_resp = mock_response(text=_TRENDING_HTML)

    with patch.object(collector.session, "get", return_value=html_resp):
        items = collector._scrape_trending_page()

    assert len(items) == 1
    assert items[0]["post_id"] == 12345


def test_scrape_trending_page_extracts_title_and_url() -> None:
    collector = StackOverflowCollector()
    html_resp = mock_response(text=_TRENDING_HTML)

    with patch.object(collector.session, "get", return_value=html_resp):
        items = collector._scrape_trending_page()

    assert items[0]["title"] == "How to use Spring Boot?"
    assert items[0]["canonical_url"] == "https://stackoverflow.com/questions/12345/how-to-use-spring-boot"


def test_scrape_trending_page_extracts_score_and_view_count() -> None:
    collector = StackOverflowCollector()
    html_resp = mock_response(text=_TRENDING_HTML)

    with patch.object(collector.session, "get", return_value=html_resp):
        items = collector._scrape_trending_page()

    assert items[0]["score"] == 15
    assert items[0]["view_count"] == 1200


def test_scrape_trending_page_extracts_published_at() -> None:
    collector = StackOverflowCollector()
    html_resp = mock_response(text=_TRENDING_HTML)

    with patch.object(collector.session, "get", return_value=html_resp):
        items = collector._scrape_trending_page()

    assert items[0]["published_at"] is not None
    assert "2026" in items[0]["published_at"]


def test_scrape_trending_page_extracts_preview() -> None:
    collector = StackOverflowCollector()
    html_resp = mock_response(text=_TRENDING_HTML)

    with patch.object(collector.session, "get", return_value=html_resp):
        items = collector._scrape_trending_page()

    assert items[0]["preview"] is not None
    assert "preview" in items[0]["preview"].lower()


def test_scrape_trending_page_returns_empty_on_empty_html() -> None:
    collector = StackOverflowCollector()
    html_resp = mock_response(text="<html></html>")

    with patch.object(collector.session, "get", return_value=html_resp):
        items = collector._scrape_trending_page()

    assert items == []


# ── _to_normalized_content ────────────────────────────────────────────────────


def _make_scraped(
    post_id: int = 1,
    title: str = "Test Question",
    canonical_url: str = "https://stackoverflow.com/questions/1/test",
    score: int = 15,
    view_count: int = 1000,
    published_at: str = "2026-03-15T10:00:00+00:00",
    preview: str = "Short preview.",
    author: str = "devuser",
) -> dict:
    return {
        "post_id": post_id,
        "title": title,
        "canonical_url": canonical_url,
        "score": score,
        "view_count": view_count,
        "published_at": published_at,
        "preview": preview,
        "author": author,
    }


def _make_api_data(
    body: str = "<p>Question body</p>",
    tags: list[str] | None = None,
    is_answered: bool = True,
) -> dict:
    return {
        "body": body,
        "tags": tags or ["java", "spring-boot"],
        "is_answered": is_answered,
    }


def _make_answer(
    body: str = "Answer body",
    is_accepted: bool = True,
    score: int = 20,
) -> dict:
    return {"body": body, "is_accepted": is_accepted, "score": score}


def test_to_normalized_content_basic_fields() -> None:
    collector = StackOverflowCollector()
    scraped = _make_scraped()
    api_data = _make_api_data()

    result = collector._to_normalized_content(scraped, api_data, [])

    assert result is not None
    assert result.source_name == "Stack Overflow"
    assert result.title == "Test Question"
    assert result.author == "devuser"
    assert result.view_count == 1000
    assert result.likes == 15
    assert result.is_original_visible is True
    assert result.license_type == "CC BY-SA 4.0"


def test_to_normalized_content_missing_canonical_url_returns_none() -> None:
    collector = StackOverflowCollector()
    scraped = _make_scraped(canonical_url=None)

    result = collector._to_normalized_content(scraped, {}, [])

    assert result is None


def test_to_normalized_content_tags_from_api() -> None:
    collector = StackOverflowCollector()
    scraped = _make_scraped()
    api_data = _make_api_data(tags=["python", "django"])

    result = collector._to_normalized_content(scraped, api_data, [])

    assert result is not None
    assert result.tags == ["python", "django"]


def test_to_normalized_content_is_answered() -> None:
    collector = StackOverflowCollector()
    scraped = _make_scraped()
    api_data = _make_api_data(is_answered=True)

    result = collector._to_normalized_content(scraped, api_data, [])

    assert result is not None
    assert result.is_answered is True


def test_to_normalized_content_question_content_from_api_body() -> None:
    collector = StackOverflowCollector()
    scraped = _make_scraped()
    api_data = _make_api_data(body="<p>Detailed question</p>")

    result = collector._to_normalized_content(scraped, api_data, [])

    assert result is not None
    assert result.question_content == "<p>Detailed question</p>"
    assert result.body_candidate == "<p>Detailed question</p>"


def test_to_normalized_content_accepted_answer_structured() -> None:
    collector = StackOverflowCollector()
    scraped = _make_scraped()
    api_data = _make_api_data()
    answers = [_make_answer(body="Best answer", is_accepted=True, score=50)]

    result = collector._to_normalized_content(scraped, api_data, answers)

    assert result is not None
    assert result.accepted_answer == {"body": "Best answer", "score": 50}


def test_to_normalized_content_top_answers_structured() -> None:
    collector = StackOverflowCollector()
    scraped = _make_scraped()
    api_data = _make_api_data()
    answers = [
        _make_answer(body="Top 1", is_accepted=False, score=30),
        _make_answer(body="Top 2", is_accepted=False, score=20),
        _make_answer(body="Top 3", is_accepted=False, score=10),
    ]

    result = collector._to_normalized_content(scraped, api_data, answers)

    assert result is not None
    assert len(result.top_answers) == 2  # max 2
    assert result.top_answers[0]["body"] == "Top 1"
    assert result.top_answers[0]["score"] == 30


def test_to_normalized_content_no_api_data_returns_content() -> None:
    """API 데이터 없어도 HTML 스크랩 데이터만으로 NormalizedContent 생성."""
    collector = StackOverflowCollector()
    scraped = _make_scraped()

    result = collector._to_normalized_content(scraped, {}, [])

    assert result is not None
    assert result.body_candidate is None
    assert result.tags == []
    assert result.is_answered is None
    assert result.accepted_answer is None
    assert result.top_answers == []


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
