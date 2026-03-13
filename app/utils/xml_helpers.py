"""Helpers for RSS/Atom raw parsing with feedparser."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
from typing import Any

import feedparser


def safe_get_text(value: Any, default: str | None = None) -> str | None:
    """Safely normalize arbitrary values to stripped string text."""
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def detect_parser_type(
    parsed_feed: feedparser.FeedParserDict, parser_type: str = "auto"
) -> str:
    """Detect rss/atom from feedparser metadata unless parser_type is explicit."""
    if parser_type in {"rss", "atom"}:
        return parser_type

    feed_version = safe_get_text(getattr(parsed_feed, "version", None), "")
    feed_namespace = safe_get_text(parsed_feed.feed.get("xmlns"), "")

    if "atom" in feed_version.lower() or "atom" in feed_namespace.lower():
        return "atom"
    if "rss" in feed_version.lower() or "rdf" in feed_version.lower():
        return "rss"

    if parsed_feed.feed.get("subtitle") and not parsed_feed.feed.get("description"):
        return "atom"
    return "rss"


def normalize_date(value: str | None) -> str | None:
    """Normalize various date strings into ISO 8601 when possible."""
    if value is None:
        return None

    candidate = value.strip()
    if not candidate:
        return None

    try:
        parsed = parsedate_to_datetime(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except (TypeError, ValueError):
        pass

    try:
        normalized = candidate.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except ValueError:
        return candidate


def sha256_text(value: str) -> str:
    """Compute SHA-256 hash for text input."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def extract_thumbnail_url(entry: Any) -> str | None:
    """Extract thumbnail image URL from feedparser entry media fields."""
    thumbnails = entry.get("media_thumbnail") or []
    if thumbnails and isinstance(thumbnails, list):
        url = safe_get_text(thumbnails[0].get("url"))
        if url:
            return url

    media_contents = entry.get("media_content") or []
    for media in media_contents:
        if isinstance(media, dict):
            media_type = safe_get_text(media.get("type"), "")
            if media_type and media_type.startswith("image/"):
                url = safe_get_text(media.get("url"))
                if url:
                    return url

    enclosures = entry.get("enclosures") or []
    for enclosure in enclosures:
        if isinstance(enclosure, dict):
            enc_type = safe_get_text(enclosure.get("type"), "")
            if enc_type and enc_type.startswith("image/"):
                url = safe_get_text(enclosure.get("href"))
                if url:
                    return url

    return None


def compute_entry_hash(
    source_name: str,
    entry_external_id: str | None,
    entry_url: str | None,
    title_raw: str | None,
    published_at_raw: str | None,
    summary_raw: str | None,
    content_raw: str | None,
) -> str:
    """Build a deterministic hash from raw entry identity/content fields."""
    data = "||".join(
        [
            source_name or "",
            entry_external_id or "",
            entry_url or "",
            title_raw or "",
            published_at_raw or "",
            summary_raw or "",
            content_raw or "",
        ]
    )
    return sha256_text(data)
