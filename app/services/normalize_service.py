"""Minimal raw-to-normalized conversion service.

Source behavior notes:
- NAVER_D2 / Toss_Tech: generally content_raw 중심 본문형
- Medium_*: content_raw 또는 summary_raw 둘 다 본문 후보 가능
- Kakao_Tech: html_text_raw 중심 본문 보강형
- Velog: 현재 보류, 이 서비스 기준에는 포함하지 않음
"""

from __future__ import annotations

import re

from app.schemas.normalized_content import NormalizedContent
from app.schemas.raw_content import RawEntry

FULL_BODY_MIN_LENGTH = 800
PARTIAL_BODY_MIN_LENGTH = 300
PREVIEW_MAX_LENGTH = 260


class NormalizeService:
    """Provides minimum normalization from raw RSS entries."""

    @staticmethod
    def text_length(value: str | None) -> int:
        """Return trimmed text length, or 0 for empty values."""
        if not value:
            return 0
        return len(value.strip())

    @staticmethod
    def clean_text(value: str | None) -> str | None:
        """Perform light cleanup for preview generation."""
        if not value:
            return None
        without_tags = re.sub(r"<[^>]+>", " ", value)
        normalized_space = re.sub(r"\s+", " ", without_tags).strip()
        return normalized_space or None

    def select_body_candidate_with_source(
        self, raw_entry: RawEntry
    ) -> tuple[str | None, str]:
        """Select body candidate and return both selected text and source field name."""
        html_text_raw = raw_entry.html_text_raw
        content_raw = raw_entry.content_raw
        summary_raw = raw_entry.summary_raw

        html_len = self.text_length(html_text_raw)
        content_len = self.text_length(content_raw)
        summary_len = self.text_length(summary_raw)

        if html_len >= PARTIAL_BODY_MIN_LENGTH:
            return html_text_raw, "crawl"

        if content_len >= FULL_BODY_MIN_LENGTH:
            return content_raw, "rss"
        if summary_len >= FULL_BODY_MIN_LENGTH:
            return summary_raw, "rss"

        if content_len >= PARTIAL_BODY_MIN_LENGTH:
            return content_raw, "rss"
        if summary_len >= PARTIAL_BODY_MIN_LENGTH:
            return summary_raw, "rss"

        return None, "none"

    def select_body_candidate(self, raw_entry: RawEntry) -> str | None:
        """Select body candidate based on configured priority and length thresholds."""
        body_candidate, _ = self.select_body_candidate_with_source(raw_entry)
        return body_candidate

    def classify_content_kind(self, body_candidate: str | None) -> str:
        """Classify content quality based on body candidate length."""
        body_length = self.text_length(body_candidate)
        if body_length >= FULL_BODY_MIN_LENGTH:
            return "full_body"
        return "preview_only"

    def build_preview(
        self, raw_entry: RawEntry, body_candidate: str | None
    ) -> str | None:
        """Build short preview from summary first, else body candidate."""
        base_text = raw_entry.summary_raw or body_candidate
        cleaned = self.clean_text(base_text)
        if not cleaned:
            return None
        return cleaned[:PREVIEW_MAX_LENGTH]

    def normalize_entry(self, raw_entry: RawEntry) -> NormalizedContent:
        """Convert one raw entry into minimum normalized content shape."""
        body_candidate, body_source = self.select_body_candidate_with_source(raw_entry)
        content_kind = self.classify_content_kind(body_candidate)
        preview = self.build_preview(raw_entry, body_candidate)

        return NormalizedContent(
            source_name=raw_entry.source_name,
            title=raw_entry.title_raw,
            canonical_url=raw_entry.entry_url,
            published_at=raw_entry.published_at_raw,
            preview=preview,
            body_candidate=body_candidate,
            body_source=body_source,
            content_kind=content_kind,
            entry_external_id=raw_entry.entry_external_id,
        )
