"""Tests for Kakao RSS+crawl enrichment collector."""

from __future__ import annotations

from datetime import datetime, timezone
import json

from app.collectors.rss_crawl import RSSCrawlCollector
from app.schemas.raw_content import RawEntry, RawFeedMeta
from app.schemas.source import SourceConfig
from app.utils.html_helpers import (
    extract_kakao_article_body,
    extract_kakao_article_body_result,
)


def test_extract_kakao_article_body_success() -> None:
    html = """
    <html><body>
      <article>
        <div class="entry-content">
          <p>Hello Kakao Tech</p>
          <div class="share">share buttons</div>
          <p>Second paragraph</p>
        </div>
      </article>
    </body></html>
    """
    body_html, body_text = extract_kakao_article_body(html)

    assert body_html is not None
    assert body_text is not None
    assert "Hello Kakao Tech" in body_text
    assert "share buttons" not in body_text


def test_extract_kakao_article_body_selector_fail_returns_none() -> None:
    html = "<html><body><div>No article body here</div></body></html>"
    body_html, body_text = extract_kakao_article_body(html)
    assert body_html is None
    assert body_text is None


def test_extract_kakao_article_body_nuxt_payload_fallback() -> None:
    long_payload = "<p>Kakao payload body text</p>" * 20
    payload = json.dumps(
        [
            ["ShallowReactive", 1],
            {"data": 2},
            ["ShallowReactive", 3],
            {"content": long_payload},
        ]
    )
    html = f"""
    <html><body>
      <script>
        {payload}
      </script>
    </body></html>
    """
    result = extract_kakao_article_body_result(html)

    assert result.body_html is not None
    assert result.body_text is not None
    assert "Kakao payload body text" in result.body_text
    assert result.method == "payload"


def test_selects_longest_meaningful_selector_candidate() -> None:
    short_text = "짧은 요약" * 8
    long_text = "긴 본문 문단입니다. " * 120
    html = f"""
    <html><body>
      <article><div class="entry-content"><p>{short_text}</p></div></article>
      <main><div class="view_cont"><p>{long_text}</p></div></main>
    </body></html>
    """

    result = extract_kakao_article_body_result(html)
    assert result.body_text is not None
    assert len(result.body_text) > 300
    assert "긴 본문 문단입니다" in result.body_text
    assert result.method == "selector"


def test_short_selector_candidate_uses_payload_fallback() -> None:
    short_text = "짧은 내용" * 10
    payload_long_html = "<p>payload long text</p>" * 100
    payload = json.dumps([["x", 1], {"post": {"content": payload_long_html}}])
    html = f"""
    <html><body>
      <article><div class="entry-content"><p>{short_text}</p></div></article>
      <script>
        {payload}
      </script>
    </body></html>
    """

    result = extract_kakao_article_body_result(html)
    assert result.body_text is not None
    assert len(result.body_text) > 500
    assert result.method == "payload"


def test_cleaning_preserves_core_text_removes_share_blocks() -> None:
    html = """
    <html><body>
      <article>
        <div class="entry-content">
          <p>핵심 본문 문장 A</p>
          <div class="share">공유 링크 모음</div>
          <div class="related-post">관련글 목록</div>
          <p>핵심 본문 문장 B</p>
        </div>
      </article>
    </body></html>
    """

    body_html, body_text = extract_kakao_article_body(html)
    assert body_html is not None
    assert body_text is not None
    assert "핵심 본문 문장 A" in body_text
    assert "핵심 본문 문장 B" in body_text
    assert "공유 링크 모음" not in body_text
    assert "관련글 목록" not in body_text


def test_rss_crawl_collector_enriches_html_text(monkeypatch) -> None:
    collector = RSSCrawlCollector(timeout=3.0, max_retries=0)

    source = SourceConfig(
        name="Kakao_Tech",
        feed_url="https://tech.kakao.com/feed/",
        site_url="https://tech.kakao.com/",
        parser_type="rss",
        content_level=1,
        active=True,
        note="Level 1 RSS + crawl",
    )

    raw_entry = RawEntry(
        source_name="Kakao_Tech",
        feed_url=source.feed_url,
        site_url=source.site_url,
        parser_type="rss",
        content_level_hint=1,
        entry_external_id="entry-1",
        entry_url="https://tech.kakao.com/posts/1",
        title_raw="Title",
        published_at_raw="2026-03-08T00:00:00+00:00",
        summary_raw="summary",
        content_raw=None,
        response_hash="resp",
        entry_hash="ehash",
        fetched_at=datetime.now(timezone.utc),
    )
    raw_meta = RawFeedMeta(
        source_name="Kakao_Tech",
        feed_url=source.feed_url,
        site_url=source.site_url,
        parser_type="rss",
        http_status=200,
        response_hash="resp",
        fetched_at=datetime.now(timezone.utc),
    )

    def fake_collect(_source: SourceConfig):
        return raw_meta, [raw_entry], "<rss></rss>"

    class DummyResponse:
        def __init__(self, text: str) -> None:
            self.text = text
            self.status_code = 200
            self.headers = {"Content-Type": "text/html; charset=utf-8"}

        def raise_for_status(self) -> None:
            return None

    html = """
    <html><body>
      <article><div class="entry-content"><p>본문 보강 텍스트</p></div></article>
    </body></html>
    """

    def fake_get(*args, **kwargs):
        return DummyResponse(html)

    monkeypatch.setattr(collector.rss_collector, "collect", fake_collect)
    monkeypatch.setattr(collector.session, "get", fake_get)

    _, enriched_entries, _ = collector.collect(source)
    assert len(enriched_entries) == 1
    assert enriched_entries[0].html_text_raw is not None
    assert "본문 보강 텍스트" in enriched_entries[0].html_text_raw
