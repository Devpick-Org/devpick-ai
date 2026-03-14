"""HTML → 구조 보존 텍스트 전처리 서비스 (DP-216)."""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup, NavigableString, Tag

from app.utils.html_helpers import NOISY_SELECTORS

# 완전 제거할 태그
_DECOMPOSE_TAGS: tuple[str, ...] = ("script", "style", "noscript", "iframe")

# 노이즈 섹션 CSS 셀렉터 (NOISY_SELECTORS 확장)
_EXTRA_NOISY_SELECTORS: tuple[str, ...] = (
    ".subscribe",
    ".newsletter",
    ".comment",
    ".comments",
    ".comment-section",
    ".pagination",
    ".breadcrumb",
    ".toc",
    ".table-of-contents",
    ".sidebar",
    "[role='navigation']",
    "[role='banner']",
    "[role='complementary']",
)

_ALL_NOISY_SELECTORS: tuple[str, ...] = NOISY_SELECTORS + _EXTRA_NOISY_SELECTORS

# 보일러플레이트 라인 (단독 줄로만 매칭)
_BOILERPLATE_LINES: frozenset[str] = frozenset(
    {
        "공유하기",
        "더보기",
        "구독하기",
        "뉴스레터 신청",
        "뉴스레터",
        "댓글",
        "목록으로",
        "이전글",
        "다음글",
        "관련글",
        "share",
        "subscribe",
        "read more",
        "see more",
        "load more",
    }
)

# 블록 태그 (앞뒤 빈 줄로 감쌀 태그)
_BLOCK_TAGS: frozenset[str] = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "main",
        "table",
        "thead",
        "tbody",
        "tr",
        "td",
        "th",
        "figure",
        "figcaption",
        "details",
        "summary",
        "ul",
        "ol",
    }
)

# 인라인 태그 (children만 재귀 처리)
_INLINE_TAGS: frozenset[str] = frozenset(
    {
        "span",
        "a",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "s",
        "del",
        "ins",
        "mark",
        "small",
        "sup",
        "sub",
        "abbr",
        "cite",
        "q",
        "label",
        "time",
    }
)

_HEADING_LEVEL: dict[str, str] = {
    "h1": "#",
    "h2": "##",
    "h3": "###",
    "h4": "####",
    "h5": "#####",
    "h6": "######",
}


def _traverse(node: Tag) -> str:
    """DOM 트리 순회 → 구조 보존 텍스트 변환."""
    parts: list[str] = []

    for child in node.children:
        if isinstance(child, NavigableString):
            text = html.unescape(str(child))
            parts.append(text)
            continue

        if not isinstance(child, Tag):
            continue

        tag = child.name

        # pre (코드 블록) — 내부 그대로 보존
        if tag == "pre":
            code_text = child.get_text()
            parts.append(f"\n\n```\n{code_text}\n```\n\n")
            continue

        # 인라인 코드
        if tag == "code":
            # pre 안에 있으면 이미 처리됨 — 여기선 인라인 code
            inline_text = child.get_text()
            parts.append(f"`{inline_text}`")
            continue

        # 제목
        if tag in _HEADING_LEVEL:
            marker = _HEADING_LEVEL[tag]
            inner = _traverse(child).strip()
            parts.append(f"\n\n{marker} {inner}\n\n")
            continue

        # 리스트 항목
        if tag == "li":
            inner = _traverse(child).strip()
            parts.append(f"\n- {inner}")
            continue

        # 이미지 — alt 텍스트 보존
        if tag == "img":
            alt = child.get("alt", "").strip()
            if alt:
                parts.append(f"[이미지: {alt}]")
            continue

        # 줄바꿈
        if tag == "br":
            parts.append("\n")
            continue

        # 수평선
        if tag == "hr":
            parts.append("\n\n---\n\n")
            continue

        # 인용
        if tag == "blockquote":
            inner = _traverse(child).strip()
            quoted = "\n".join(f"> {line}" for line in inner.splitlines())
            parts.append(f"\n\n{quoted}\n\n")
            continue

        # 블록 태그
        if tag in _BLOCK_TAGS:
            inner = _traverse(child)
            parts.append(f"\n\n{inner}\n\n")
            continue

        # 인라인 태그
        if tag in _INLINE_TAGS:
            parts.append(_traverse(child))
            continue

        # 알 수 없는 태그 — children만 재귀
        parts.append(_traverse(child))

    return "".join(parts)


def _normalize_whitespace(text: str) -> str:
    """공백 정규화 — 코드블록 구간은 건드리지 않는다."""
    # ``` 기준으로 분리 (코드블록 보호)
    parts = re.split(r"(```[\s\S]*?```)", text)

    result: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # 코드블록 — 그대로
            result.append(part)
        else:
            # 일반 텍스트 정규화
            part = part.replace("\t", " ")
            part = re.sub(r"[ \t]+", " ", part)  # 연속 공백 → 1칸
            part = re.sub(r"\n{3,}", "\n\n", part)  # 3+ 줄바꿈 → 2줄
            result.append(part)

    return "".join(result)


def _remove_boilerplate(text: str) -> str:
    """보일러플레이트 라인 제거 — 단독 줄로 정확히 매칭되는 경우만."""
    lines = text.splitlines()
    filtered = [
        line for line in lines if line.strip().lower() not in _BOILERPLATE_LINES
    ]
    return "\n".join(filtered)


class PreprocessService:
    """HTML → 구조 보존 텍스트 전처리 서비스."""

    def preprocess(self, html_input: str) -> str:
        """HTML 문자열을 구조 보존 텍스트로 변환한다.

        Args:
            html_input: 원본 HTML 문자열.

        Returns:
            구조 보존 텍스트.

        Raises:
            ValueError: 본문이 비어 있거나 추출 불가능한 경우.
        """
        soup = BeautifulSoup(html_input, "html.parser")

        # ① 완전 제거 태그 decompose
        for tag_name in _DECOMPOSE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # ② 노이즈 섹션 decompose
        for selector in _ALL_NOISY_SELECTORS:
            for node in soup.select(selector):
                node.decompose()

        # ③ DOM 순회 → 구조 보존 텍스트 변환
        raw_text = _traverse(soup)

        # ④ 공백 정규화
        normalized = _normalize_whitespace(raw_text)

        # ⑤ 보일러플레이트 라인 제거
        cleaned = _remove_boilerplate(normalized)

        result = cleaned.strip()

        # ⑥ 빈 결과 검사
        if not result:
            raise ValueError("요약 불가: 본문 없음")

        return result
