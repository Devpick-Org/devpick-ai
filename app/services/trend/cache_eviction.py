"""BE Redis 캐시 무효화 클라이언트 (DP-387)."""

from __future__ import annotations

import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)


class CacheEvictionClient:
    """BE DELETE /internal/trends/cache 를 호출해 Redis 캐시를 무효화한다.

    best-effort — 실패해도 예외를 전파하지 않는다.
    배치 완료 직후 호출되며, 실패 시 BE Redis TTL 만료 후 자동 갱신된다.
    """

    def __init__(self, base_url: str, evict_key: str, timeout: float = 5.0) -> None:
        self._url = base_url.rstrip("/") + "/internal/trends/cache"
        self._headers = {"X-Internal-Key": evict_key}
        self._timeout = timeout

    def evict(self, unit: str, period_start: date, scope: str = "global") -> None:
        """캐시 무효화를 요청한다. 실패해도 예외를 전파하지 않는다."""
        params = {
            "unit": unit,
            "scope": scope,
            "periodStart": str(period_start),
        }
        try:
            resp = requests.delete(
                self._url,
                headers=self._headers,
                params=params,
                timeout=self._timeout,
            )
            if resp.status_code == 204:
                logger.info(
                    "캐시 무효화 완료: unit=%s period_start=%s", unit, period_start
                )
            else:
                logger.warning(
                    "캐시 무효화 실패: unit=%s period_start=%s status=%d body=%s",
                    unit,
                    period_start,
                    resp.status_code,
                    resp.text[:200],
                )
        except Exception as exc:
            logger.warning("캐시 무효화 요청 오류 (best-effort): %s", exc)
