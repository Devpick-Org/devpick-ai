"""HTML extraction helpers for RSS+crawl enrichment."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

KAKAO_BODY_SELECTORS: tuple[str, ...] = (
    "article",
    "main article",
    "main .content-article",
    "main .inner_content",
    "main .wrap_content",
    "main",
    ".article",
    ".post",
    ".post-body",
    ".entry-body",
    ".entry-content",
    ".wrap_view",
    ".view_cont",
    ".content-article",
    ".content-article article",
    ".article_view",
    ".content-article .inner_content",
    ".content-article .wrap_content",
    ".daum-wm-content.preview",
    ".wrap_content .inner_content",
    "article .entry-content",
    "article .post-content",
    "article .contents",
    ".kakaoContent .entry-content",
    ".article_view",
    ".post .entry-content",
)

NOISY_SELECTORS: tuple[str, ...] = (
    "header",
    "footer",
    "nav",
    "aside",
    ".related-post",
    ".related-article",
    ".recommend",
    ".recommended",
    ".related",
    ".share",
    ".social",
    ".ad",
    ".ads",
    ".banner",
    ".author",
    ".writer",
    ".tag_list",
    ".box_btn",
    ".cont_other",
    ".box_cont",
    ".inner_footer",
    ".section_sitemap",
    ".doc-footer",
)

NUXT_HTML_MARKERS: tuple[str, ...] = (
    "<p",
    "<div",
    "<section",
    "<h2",
    "<h3",
    "<h4",
    "<ul",
    "<ol",
    "<figure",
    "<pre",
    "<code",
    "<blockquote",
)

PAYLOAD_BODY_KEYWORDS: tuple[str, ...] = (
    "content",
    "body",
    "article",
    "post",
    "description",
    "html",
    "renderedhtml",
    "richtext",
)

MIN_MEANINGFUL_TEXT_LENGTH = 150


@dataclass
class ExtractionResult:
    """Detailed extraction result for debugging/logging."""

    body_html: str | None
    body_text: str | None
    method: str | None
    detail: str | None
    selectors_tried: int
    best_text_len: int
    fallback_used: bool


def html_to_text(html: str | None) -> str | None:
    """Convert HTML snippet to normalized plain text."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized or None


def _strip_noisy_nodes(node: BeautifulSoup) -> None:
    for noisy_selector in NOISY_SELECTORS:
        for noisy_node in node.select(noisy_selector):
            noisy_node.decompose()


def _score_candidate(html_fragment: str, text: str) -> float:
    """Score content candidates to prefer article-like rich text blocks."""
    soup = BeautifulSoup(html_fragment, "html.parser")

    paragraph_count = len(soup.find_all("p"))
    list_item_count = len(soup.find_all("li"))
    code_count = len(soup.find_all(["pre", "code"]))
    heading_count = len(soup.find_all(["h2", "h3", "h4"]))

    link_text_len = sum(
        len(link.get_text(" ", strip=True)) for link in soup.find_all("a")
    )
    text_len = max(len(text), 1)
    link_density = link_text_len / text_len

    structure_bonus = (
        paragraph_count * 24
        + list_item_count * 8
        + code_count * 35
        + heading_count * 16
    )
    link_penalty = int(link_density * 260)

    return float(text_len + structure_bonus - link_penalty)


def _build_candidate(
    html_fragment: str, method: str, detail: str
) -> dict[str, Any] | None:
    """Build normalized candidate record if text is extractable."""
    text = html_to_text(html_fragment)
    if not text:
        return None

    return {
        "html": html_fragment,
        "text": text,
        "method": method,
        "detail": detail,
        "text_len": len(text),
        "score": _score_candidate(html_fragment, text),
    }


def _extract_by_selectors(
    soup: BeautifulSoup,
) -> tuple[str | None, str | None, str | None]:
    """Try known selector candidates and return highest-scoring body candidate."""
    candidates: list[dict[str, Any]] = []

    for selector in KAKAO_BODY_SELECTORS:
        matched_nodes = soup.select(selector)
        if not matched_nodes:
            continue

        for index, node in enumerate(matched_nodes):
            node_soup = BeautifulSoup(str(node), "html.parser")
            _strip_noisy_nodes(node_soup)
            candidate_html = str(node_soup)
            candidate = _build_candidate(
                candidate_html, "selector", f"{selector}[{index}]"
            )
            if candidate is not None:
                candidates.append(candidate)

    if not candidates:
        return None, None, None

    best = max(candidates, key=lambda item: item["score"])
    return best["html"], best["text"], best["detail"]


def _join_path(path: list[str]) -> str:
    return ".".join(path) if path else "root"


def _is_body_key_path(path: list[str]) -> bool:
    lowered = ".".join(path).lower()
    return any(keyword in lowered for keyword in PAYLOAD_BODY_KEYWORDS)


def _candidate_from_payload_string(
    value: str, path: list[str]
) -> dict[str, Any] | None:
    stripped = value.strip()
    if not stripped:
        return None

    path_hint = _is_body_key_path(path)
    has_html_marker = any(marker in stripped.lower() for marker in NUXT_HTML_MARKERS)

    if not (path_hint or has_html_marker):
        return None

    candidate = _build_candidate(stripped, "payload", _join_path(path))
    if candidate is None:
        return None

    if path_hint:
        candidate["score"] += 120
    if has_html_marker:
        candidate["score"] += 60
    return candidate


def _walk_payload_candidates(
    value: Any, path: list[str], out: list[dict[str, Any]]
) -> None:
    if isinstance(value, str):
        candidate = _candidate_from_payload_string(value, path)
        if candidate is not None:
            out.append(candidate)
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            _walk_payload_candidates(item, [*path, str(index)], out)
        return

    if isinstance(value, dict):
        for key, item in value.items():
            _walk_payload_candidates(item, [*path, str(key)], out)
        return


def _extract_from_nuxt_payload(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Fallback for pages where article content is hydrated from Nuxt payload JSON."""
    script_texts = [
        (script.get_text() or "").strip()
        for script in soup.find_all("script")
        if not script.get("src")
        and (script.get_text() or "").strip()
        and (script.get_text() or "").strip()[0] in "[{"
    ]
    if not script_texts:
        return None, None

    candidates: list[dict[str, Any]] = []
    for script_text in script_texts:
        try:
            payload = json.loads(script_text)
        except json.JSONDecodeError:
            continue

        _walk_payload_candidates(payload, [], candidates)

    if not candidates:
        return None, None

    best = max(candidates, key=lambda item: item["score"])
    return best["html"], best["text"]


def extract_first_image(html: str, base_url: str | None = None) -> str | None:
    """Extract the first usable image URL from HTML body content.

    Skips data: URIs. Resolves relative URLs using base_url if provided.
    """
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src", "").strip()
        if not src or src.startswith("data:"):
            continue
        if base_url and not src.startswith(("http://", "https://")):
            src = urljoin(base_url, src)
        return src or None
    return None


def extract_og_meta(html: str, prop: str) -> str | None:
    """Extract an Open Graph or standard meta property from HTML.

    Checks both ``property="..."`` and ``name="..."`` attributes so it works
    for og:title, og:description, og:image, twitter:image, author, etc.
    """
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
    if tag and tag.get("content"):
        return tag["content"].strip() or None
    return None


def extract_og_image(html: str) -> str | None:
    """Extract representative image URL from HTML meta tags."""
    return extract_og_meta(html, "og:image") or extract_og_meta(html, "twitter:image")


def extract_meta_author(html: str) -> str | None:
    """Extract author name from <meta name="author"> tag."""
    return extract_og_meta(html, "author")


def extract_article_body(html: str) -> tuple[str | None, str | None]:
    """Extract body HTML and plain text from the first <article> element.

    Strips noisy child nodes (nav, aside, footer, .related-*, etc.) before
    returning.  Returns (body_html, body_text); both None if no <article>
    found or content is too short.
    """
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article")
    if not article:
        return None, None

    _strip_noisy_nodes(article)
    body_html = str(article)
    body_text = html_to_text(body_html)
    return body_html, body_text


def extract_jsonld_field(html: str, field: str) -> str | None:
    """Extract a field from the first JSON-LD <script> block.

    More reliable than regex because it parses the full JSON structure,
    which handles whitespace, escaping, and nested objects correctly.
    Common fields: 'datePublished', 'dateModified', 'author', 'name'.
    """
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        text = (script.string or "").strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        # data may be a dict or a list of dicts
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and field in item:
                    return str(item[field]).strip() or None
        elif isinstance(data, dict) and field in data:
            return str(data[field]).strip() or None
    return None


def strip_wayback_prefix(url: str) -> str:
    """Remove Wayback Machine URL prefix from a URL.

    e.g. ``https://web.archive.org/web/20240101120000/https://example.com/img.jpg``
    → ``https://example.com/img.jpg``

    Also handles image-specific variant ``/web/20240101120000im_/...``.
    Returns the original URL unchanged if it does not contain a Wayback prefix.
    """
    if "web.archive.org" not in url:
        return url
    m = re.search(r"https?://web\.archive\.org/web/\d+(?:im_)?/(https?://.+)", url)
    return m.group(1) if m else url


def extract_kakao_article_body_result(html: str) -> ExtractionResult:
    """Extract Kakao article body and include debug metadata for logging."""
    soup = BeautifulSoup(html, "html.parser")
    selectors_tried = len(KAKAO_BODY_SELECTORS)

    selector_html, selector_text, selector_detail = _extract_by_selectors(soup)
    selector_len = len(selector_text or "")

    if selector_html and selector_text and selector_len >= MIN_MEANINGFUL_TEXT_LENGTH:
        return ExtractionResult(
            body_html=selector_html,
            body_text=selector_text,
            method="selector",
            detail=selector_detail,
            selectors_tried=selectors_tried,
            best_text_len=selector_len,
            fallback_used=False,
        )

    payload_html, payload_text = _extract_from_nuxt_payload(soup)
    payload_len = len(payload_text or "")
    if payload_html and payload_text and payload_len >= MIN_MEANINGFUL_TEXT_LENGTH:
        return ExtractionResult(
            body_html=payload_html,
            body_text=payload_text,
            method="payload",
            detail="nuxt_payload",
            selectors_tried=selectors_tried,
            best_text_len=max(selector_len, payload_len),
            fallback_used=True,
        )

    if selector_html and selector_text:
        return ExtractionResult(
            body_html=selector_html,
            body_text=selector_text,
            method="selector_short",
            detail=selector_detail,
            selectors_tried=selectors_tried,
            best_text_len=selector_len,
            fallback_used=payload_html is not None,
        )

    if payload_html and payload_text:
        return ExtractionResult(
            body_html=payload_html,
            body_text=payload_text,
            method="payload_short",
            detail="nuxt_payload",
            selectors_tried=selectors_tried,
            best_text_len=payload_len,
            fallback_used=True,
        )

    return ExtractionResult(
        body_html=None,
        body_text=None,
        method=None,
        detail=None,
        selectors_tried=selectors_tried,
        best_text_len=0,
        fallback_used=False,
    )


def extract_kakao_article_body(html: str) -> tuple[str | None, str | None]:
    """Extract Kakao Tech article body HTML and plain text.

    Returns:
        (body_html, body_text). If no matching selector is found, returns (None, None).
    """
    result = extract_kakao_article_body_result(html)
    return result.body_html, result.body_text
