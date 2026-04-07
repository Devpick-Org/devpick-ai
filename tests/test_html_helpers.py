"""Tests for Kakao article body extraction helpers."""

from __future__ import annotations

import json

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
