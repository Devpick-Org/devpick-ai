"""Unit tests for minimum raw-to-normalized conversion rules."""

from __future__ import annotations

from app.schemas.raw_content import RawEntry
from app.services.normalize_service import NormalizeService


def make_raw_entry(
    content_raw: str | None,
    summary_raw: str | None,
    html_text_raw: str | None = None,
    entry_external_id: str = "entry-1",
) -> RawEntry:
    return RawEntry(
        source_name="NAVER_D2",
        feed_url="https://example.com/feed",
        site_url="https://example.com",
        parser_type="rss",
        content_level_hint=2,
        entry_external_id=entry_external_id,
        entry_url="https://example.com/post/1",
        title_raw="Example Title",
        author_raw="Author",
        published_at_raw="2026-03-08T00:00:00+00:00",
        summary_raw=summary_raw,
        content_raw=content_raw,
        html_text_raw=html_text_raw,
        categories_raw=["dev"],
        raw_xml_fragment=None,
        response_hash="resp-hash",
        entry_hash="entry-hash",
    )


def test_select_body_candidate_prefers_content_raw() -> None:
    normalizer = NormalizeService()
    content_text = "c" * 900
    summary_text = "s" * 950
    raw_entry = make_raw_entry(content_raw=content_text, summary_raw=summary_text)

    selected = normalizer.select_body_candidate(raw_entry)
    assert selected == content_text


def test_select_body_candidate_summary_fallback() -> None:
    normalizer = NormalizeService()
    raw_entry = make_raw_entry(content_raw="c" * 120, summary_raw="s" * 450)

    selected = normalizer.select_body_candidate(raw_entry)
    assert selected == "s" * 450


def test_select_body_candidate_prefers_html_text_full_body() -> None:
    normalizer = NormalizeService()
    raw_entry = make_raw_entry(
        content_raw=None,
        summary_raw="s" * 120,
        html_text_raw="h" * 1000,
    )

    normalized = normalizer.normalize_entry(raw_entry)
    assert normalized.body_candidate == "h" * 1000
    assert normalized.body_source == "crawl"
    assert normalized.content_kind == "full_body"


def test_select_body_candidate_prefers_html_text_even_if_content_is_longer() -> None:
    normalizer = NormalizeService()
    raw_entry = make_raw_entry(
        content_raw="c" * 2000,
        summary_raw="s" * 100,
        html_text_raw="h" * 500,
    )

    normalized = normalizer.normalize_entry(raw_entry)
    assert normalized.body_candidate == "h" * 500
    assert normalized.body_source == "crawl"
    assert normalized.content_kind == "preview_only"


def test_existing_content_summary_rules_work_when_html_missing() -> None:
    normalizer = NormalizeService()
    raw_entry = make_raw_entry(
        content_raw="c" * 350,
        summary_raw="s" * 1200,
        html_text_raw=None,
    )

    normalized = normalizer.normalize_entry(raw_entry)
    assert normalized.body_candidate == "s" * 1200
    assert normalized.body_source == "rss"
    assert normalized.content_kind == "full_body"


def test_preview_only_when_both_short() -> None:
    normalizer = NormalizeService()
    raw_entry = make_raw_entry(
        content_raw="c" * 120, summary_raw="s" * 180, html_text_raw="h" * 80
    )

    normalized = normalizer.normalize_entry(raw_entry)
    assert normalized.body_candidate is None
    assert normalized.body_source == "none"
    assert normalized.content_kind == "preview_only"


def test_preview_generation_prefers_summary_and_cleans_html() -> None:
    normalizer = NormalizeService()
    summary_with_html = "<p> Hello   <b>DevPick</b> RSS </p>" + ("x" * 400)
    raw_entry = make_raw_entry(content_raw="c" * 820, summary_raw=summary_with_html)

    normalized = normalizer.normalize_entry(raw_entry)
    assert normalized.preview is not None
    assert "<" not in normalized.preview
    assert normalized.preview.startswith("Hello DevPick RSS")
    assert len(normalized.preview) <= 260
