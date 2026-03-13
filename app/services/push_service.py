"""Backend ingest push service — sends normalized content via HTTP POST."""

from __future__ import annotations

import logging

import requests

from app.schemas.normalized_content import NormalizedContent

logger = logging.getLogger(__name__)


class PushService:
    """Pushes normalized content items to the Backend ingest API."""

    def __init__(self, backend_url: str, timeout: int = 30) -> None:
        self.ingest_url = f"{backend_url}/internal/contents"
        self.timeout = timeout

    def push(self, items: list[NormalizedContent]) -> dict:
        """POST normalized content list to Backend ingest endpoint.

        Returns the parsed JSON response, e.g. {"saved": 5, "skipped": 1}.
        Raises requests.HTTPError on 4xx/5xx, requests.Timeout on timeout.
        """
        if not items:
            logger.info("push called with empty list — skipping")
            return {"saved": 0, "skipped": 0}

        payload = [item.model_dump() for item in items]
        logger.info("Pushing %d items to %s", len(items), self.ingest_url)

        response = requests.post(self.ingest_url, json=payload, timeout=self.timeout)
        response.raise_for_status()

        result: dict = response.json()
        logger.info("Backend response: %s", result)
        return result
