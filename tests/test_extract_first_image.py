"""Unit tests for extract_first_image HTML helper."""

from __future__ import annotations

from app.utils.html_helpers import extract_first_image


def test_extract_first_image_basic() -> None:
    html = '<p>text</p><img src="https://cdn.example.com/photo.jpg" />'
    assert extract_first_image(html) == "https://cdn.example.com/photo.jpg"


def test_extract_first_image_skips_data_uri() -> None:
    html = '<img src="data:image/png;base64,abc123" /><img src="https://cdn.example.com/real.png" />'
    assert extract_first_image(html) == "https://cdn.example.com/real.png"


def test_extract_first_image_resolves_relative() -> None:
    html = '<img src="/content/images/2026/03/photo.png" />'
    result = extract_first_image(html, base_url="https://d2.naver.com")
    assert result == "https://d2.naver.com/content/images/2026/03/photo.png"


def test_extract_first_image_returns_none_for_no_img() -> None:
    html = "<p>no images here</p><div>just text</div>"
    assert extract_first_image(html) is None


def test_extract_first_image_returns_none_for_empty_html() -> None:
    assert extract_first_image("") is None


def test_extract_first_image_skips_empty_src() -> None:
    html = '<img src="" /><img src="https://cdn.example.com/real.png" />'
    assert extract_first_image(html) == "https://cdn.example.com/real.png"
