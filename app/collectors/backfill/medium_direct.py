"""Medium publication backfill via internal JSON API + direct curl_cffi fetch."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from app.collectors.backfill.base import BackfillCollector
from app.schemas.raw_content import RawEntry
from app.schemas.source import SourceConfig
from app.utils.html_helpers import (
    extract_article_body,
    extract_jsonld_field,
    extract_meta_author,
    extract_og_meta,
)
from app.utils.xml_helpers import compute_entry_hash, sha256_text

logger = logging.getLogger(__name__)

MEDIUM_BASE = "https://medium.com"
_STREAM_API = MEDIUM_BASE + "/_/api/collections/{collection_id}/stream"


class MediumDirectBackfillCollector(BackfillCollector):
    """Crawl Medium publication via internal JSON API + direct curl_cffi fetch.

    Discovery: ``medium.com/{publication}?format=json``  →  collection_id + posts
    Pagination: ``/_/api/collections/{id}/stream?to={token}&limit=25``
    Fetch: curl_cffi Chrome impersonation to bypass Cloudflare / JS rendering

    Two phases:

    * **backfill** — paginate stream API newest-first until createdAt < since_ms.
      Transitions to incremental when discovery_done.

    * **incremental** — re-scans the first stream page each run, collecting only
      URLs not already in ``seen_urls``.  Never marks ``done: True``.

    Cursor format::

        {"phase": "backfill",    "collection_id": "...", "next_to": null,
         "discovery_done": false, "pending": [["slug", ms], ...], "seen_urls": [...]}
        {"phase": "incremental", "collection_id": "...", "seen_urls": [...]}
    """

    def __init__(
        self,
        publication: str,
        since: str = "2026-01-01",
        timeout: float = 20.0,
        delay: float = 2.0,
    ) -> None:
        self.publication = publication
        self.since = since
        self.since_ms = int(
            datetime.strptime(since, "%Y-%m-%d")
            .replace(tzinfo=timezone.utc)
            .timestamp()
            * 1000
        )
        self.timeout = timeout
        self.delay = delay

    # ------------------------------------------------------------------
    # BackfillCollector interface
    # ------------------------------------------------------------------

    def collect_batch(
        self, source: SourceConfig, cursor: dict, batch_size: int = 20
    ) -> tuple[list[RawEntry], dict]:
        phase = self._resolve_phase(cursor)

        if phase == "incremental":
            return self._collect_incremental(source, cursor, batch_size)
        return self._collect_backfill(source, cursor, batch_size)

    # ------------------------------------------------------------------
    # Backfill phase
    # ------------------------------------------------------------------

    def _collect_backfill(
        self, source: SourceConfig, cursor: dict, batch_size: int
    ) -> tuple[list[RawEntry], dict]:
        pending: list[list] = list(cursor.get("pending", []))
        seen_urls: set[str] = set(cursor.get("seen_urls", []))
        collection_id: str | None = cursor.get("collection_id")
        next_to: str | None = cursor.get("next_to")
        discovery_done: bool = cursor.get("discovery_done", False)

        with cffi_requests.Session() as session:
            if not discovery_done:
                if not collection_id:
                    collection_id = self._get_collection_id(session)
                    if not collection_id:
                        logger.warning(
                            "Medium/%s: cannot find collection_id, retry next run",
                            self.publication,
                        )
                        return [], cursor

                new_slugs, next_to, discovery_done = self._discover_page(
                    session, collection_id, next_to, seen_urls
                )
                pending.extend(new_slugs)

            to_fetch = pending[:batch_size]
            remaining = pending[batch_size:]

            entries: list[RawEntry] = []
            for slug, created_ms in to_fetch:
                url = f"{MEDIUM_BASE}/{self.publication}/{slug}"
                entry = self._fetch_article(session, source, url, created_ms)
                if entry is not None:
                    entries.append(entry)
                seen_urls.add(url)
                time.sleep(self.delay)

        if discovery_done and len(remaining) == 0:
            logger.info(
                "Medium/%s backfill complete — transitioning to incremental",
                self.publication,
            )
            return entries, {
                "phase": "incremental",
                "collection_id": collection_id,
                "seen_urls": list(seen_urls),
            }

        return entries, {
            "phase": "backfill",
            "collection_id": collection_id,
            "next_to": next_to,
            "discovery_done": discovery_done,
            "pending": remaining,
            "seen_urls": list(seen_urls),
        }

    # ------------------------------------------------------------------
    # Incremental phase
    # ------------------------------------------------------------------

    def _collect_incremental(
        self, source: SourceConfig, cursor: dict, batch_size: int
    ) -> tuple[list[RawEntry], dict]:
        """Re-scan first stream page; collect any URLs not yet in seen_urls."""
        seen_urls: set[str] = set(cursor.get("seen_urls", []))
        collection_id: str | None = cursor.get("collection_id")

        with cffi_requests.Session() as session:
            if not collection_id:
                collection_id = self._get_collection_id(session)
                if not collection_id:
                    logger.warning(
                        "Medium/%s incremental: cannot find collection_id",
                        self.publication,
                    )
                    return [], cursor

            # Scan first page only (newest articles)
            new_slugs, _, _ = self._discover_page(
                session, collection_id, next_to=None, seen_urls=seen_urls
            )

            if not new_slugs:
                logger.info("Medium/%s incremental: no new articles", self.publication)
                return [], {
                    "phase": "incremental",
                    "collection_id": collection_id,
                    "seen_urls": list(seen_urls),
                }

            to_fetch = new_slugs[:batch_size]
            entries: list[RawEntry] = []
            for slug, created_ms in to_fetch:
                url = f"{MEDIUM_BASE}/{self.publication}/{slug}"
                entry = self._fetch_article(session, source, url, created_ms)
                if entry is not None:
                    entries.append(entry)
                seen_urls.add(url)
                time.sleep(self.delay)

        logger.info(
            "Medium/%s incremental: found %d new articles",
            self.publication,
            len(entries),
        )
        return entries, {
            "phase": "incremental",
            "collection_id": collection_id,
            "seen_urls": list(seen_urls),
        }

    # ------------------------------------------------------------------
    # Discovery helpers
    # ------------------------------------------------------------------

    def _get_collection_id(self, session: cffi_requests.Session) -> str | None:
        """Fetch publication main page JSON to extract collection_id."""
        try:
            resp = session.get(
                f"{MEDIUM_BASE}/{self.publication}?format=json",
                impersonate="chrome",
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except Exception as err:
            logger.warning(
                "Medium/%s: main page JSON fetch failed: %s", self.publication, err
            )
            return None

        data = self._parse_medium_json(resp.text)
        if data is None:
            return None

        collection = data.get("payload", {}).get("references", {}).get("Collection", {})
        if collection:
            cid = next(iter(collection))
            logger.info("Medium/%s: resolved collection_id=%s", self.publication, cid)
            return cid

        logger.warning("Medium/%s: no Collection in JSON payload", self.publication)
        return None

    def _discover_page(
        self,
        session: cffi_requests.Session,
        collection_id: str,
        next_to: str | None,
        seen_urls: set[str],
    ) -> tuple[list[list], str | None, bool]:
        """Fetch one page from the collection stream API.

        Returns (new_slugs, next_to_token, discovery_done).
        """
        url = _STREAM_API.format(collection_id=collection_id)
        params: dict = {"limit": 25}
        if next_to:
            params["to"] = next_to

        try:
            resp = session.get(
                url, params=params, impersonate="chrome", timeout=self.timeout
            )
            resp.raise_for_status()
        except Exception as err:
            logger.warning("Medium/%s: stream API failed: %s", self.publication, err)
            return [], next_to, False

        data = self._parse_medium_json(resp.text)
        if data is None:
            return [], next_to, False

        payload = data.get("payload", {})
        posts = payload.get("references", {}).get("Post", {})
        paging = payload.get("paging", {})
        next_page = paging.get("next")

        new_slugs: list[list] = []
        hit_pre_since = False

        for _pid, post in posts.items():
            created_ms = post.get("createdAt", 0)
            if created_ms < self.since_ms:
                hit_pre_since = True
                continue
            slug = post.get("uniqueSlug", "")
            if not slug:
                continue
            article_url = f"{MEDIUM_BASE}/{self.publication}/{slug}"
            if article_url not in seen_urls:
                new_slugs.append([slug, created_ms])

        discovery_done = hit_pre_since or (next_page is None)
        next_to_out = next_page.get("to") if next_page and not discovery_done else None

        logger.info(
            "Medium/%s stream page: %d new slugs, discovery_done=%s",
            self.publication,
            len(new_slugs),
            discovery_done,
        )
        return new_slugs, next_to_out, discovery_done

    # ------------------------------------------------------------------
    # Article fetch
    # ------------------------------------------------------------------

    def _fetch_article(
        self,
        session: cffi_requests.Session,
        source: SourceConfig,
        url: str,
        created_ms: int,
    ) -> RawEntry | None:
        try:
            resp = session.get(
                url, impersonate="chrome", timeout=self.timeout, verify=False
            )
            resp.raise_for_status()
        except Exception as err:
            logger.warning(
                "Medium/%s article %s failed: %s", self.publication, url, err
            )
            return None

        html = resp.text
        # Use final URL after redirects (e.g. netflixtechblog.com) as canonical
        canonical_url = resp.url or url

        title = (
            extract_og_meta(html, "og:title")
            or extract_jsonld_field(html, "headline")
            or extract_jsonld_field(html, "name")
        )
        thumbnail_url = extract_og_meta(html, "og:image") or None
        body_html, body_text = extract_article_body(html)
        published_at = extract_jsonld_field(html, "datePublished") or (
            datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).isoformat()
        )
        author = extract_meta_author(html)

        response_hash = sha256_text(html)
        entry_hash = compute_entry_hash(
            source_name=source.name,
            entry_external_id=canonical_url,
            entry_url=canonical_url,
            title_raw=title,
            published_at_raw=published_at,
            summary_raw=None,
            content_raw=None,
        )

        logger.info(
            "Medium/%s article %s title=%s date=%s body_len=%d",
            self.publication,
            canonical_url.split("/")[-1][:30],
            (title or "?")[:40],
            published_at or "?",
            len(body_text or ""),
        )

        return RawEntry(
            source_name=source.name,
            feed_url=source.feed_url,
            site_url=source.site_url,
            parser_type="backfill",
            content_level_hint=1,
            entry_external_id=canonical_url,
            entry_url=canonical_url,
            title_raw=title,
            author_raw=author,
            published_at_raw=published_at,
            summary_raw=None,
            content_raw=None,
            html_body_raw=body_html,
            html_text_raw=body_text if body_text and len(body_text) > 100 else None,
            thumbnail_url=thumbnail_url,
            categories_raw=[],
            fetched_at=datetime.now(timezone.utc),
            response_hash=response_hash,
            parser_version="backfill-medium-direct-v1",
            entry_hash=entry_hash,
        )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_medium_json(text: str) -> dict | None:
        stripped = text.lstrip("])}while(1);</x>")
        try:
            return json.loads(stripped)
        except Exception:
            return None
