"""Unit tests for RSS/XML parsing utility helpers."""

from __future__ import annotations

import feedparser

from app.utils.xml_helpers import (
    compute_entry_hash,
    detect_parser_type,
    normalize_date,
    safe_get_text,
    sha256_text,
)


def test_detect_parser_type_rss_and_atom() -> None:
    rss_xml = """<?xml version=\"1.0\"?><rss version=\"2.0\"><channel><title>x</title></channel></rss>"""
    atom_xml = """<?xml version=\"1.0\"?><feed xmlns=\"http://www.w3.org/2005/Atom\"><title>x</title></feed>"""

    parsed_rss = feedparser.parse(rss_xml)
    parsed_atom = feedparser.parse(atom_xml)

    assert detect_parser_type(parsed_rss, "auto") == "rss"
    assert detect_parser_type(parsed_atom, "auto") == "atom"


def test_hash_helpers_are_deterministic() -> None:
    first = sha256_text("hello")
    second = sha256_text("hello")
    assert first == second

    entry_hash_a = compute_entry_hash(
        source_name="source",
        entry_external_id="id-1",
        entry_url="https://example.com/post",
        title_raw="title",
        published_at_raw="2026-03-07T00:00:00+00:00",
        summary_raw="summary",
        content_raw="content",
    )
    entry_hash_b = compute_entry_hash(
        source_name="source",
        entry_external_id="id-1",
        entry_url="https://example.com/post",
        title_raw="title",
        published_at_raw="2026-03-07T00:00:00+00:00",
        summary_raw="summary",
        content_raw="content",
    )
    assert entry_hash_a == entry_hash_b


def test_normalize_date_and_safe_text() -> None:
    assert normalize_date("2026-03-07T12:00:00Z") == "2026-03-07T12:00:00+00:00"
    assert safe_get_text("  hello ") == "hello"
    assert safe_get_text(None, "fallback") == "fallback"


def test_feedparser_parse_sample_rss() -> None:
    rss_xml = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version=\"2.0\">
  <channel>
    <title>Sample Feed</title>
    <item><title>Post 1</title><link>https://example.com/p1</link></item>
  </channel>
</rss>
"""
    parsed = feedparser.parse(rss_xml)
    assert parsed.feed.get("title") == "Sample Feed"
    assert len(parsed.entries) == 1
