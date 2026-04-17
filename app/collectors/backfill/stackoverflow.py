"""Stack Overflow backfill + incremental collector.

수집 전략:
- backfill phase: SO API v2.3 월별 date window (sort=hot, fromdate/todate)
  - 2026-01 ~ 현재 월까지 순차 수집 (월별 batch_size개)
  - 현재 월 완료 시 → incremental phase 전환
- incremental phase: 트렌딩 페이지 HTML 크롤링 (매 실행마다 최신 trending 수집)

커서 형식:
  backfill:    {"phase": "backfill", "year": 2026, "month": 1}
  incremental: {"phase": "incremental"}
"""

from __future__ import annotations

import calendar
import logging
import re
from datetime import date, datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.collectors.stackoverflow import StackOverflowCollector, _build_body_candidate
from app.schemas.normalized_content import NormalizedContent

logger = logging.getLogger(__name__)

_BASE_API_URL = "https://api.stackexchange.com/2.3"
_SITE = "stackoverflow"
_LICENSE_TYPE = "CC BY-SA 4.0"
_TOP_ANSWER_LIMIT = 2
_PREVIEW_MAX_LENGTH = 300
_BACKFILL_START_YEAR = 2026
_BACKFILL_START_MONTH = 1


class StackOverflowBackfillCollector:
    """Monthly backfill + incremental trending collector for Stack Overflow.

    BackfillCollector 인터페이스를 따르지 않고 NormalizedContent를 직접 반환한다.
    run_backfill_batch.py의 _DIRECT_COLLECTOR_FACTORIES에 등록해서 사용한다.

    Usage:
        collector = StackOverflowBackfillCollector(api_key="...")
        items, new_cursor = collector.collect_batch_normalized(cursor, batch_size=20)
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 15.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key or ""
        self.timeout = timeout
        self._trending = StackOverflowCollector(
            api_key=api_key, timeout=timeout, max_retries=max_retries
        )
        self.session = requests.Session()

        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET"]),
            backoff_factor=1.0,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def collect_batch_normalized(
        self, cursor: dict, batch_size: int = 20
    ) -> tuple[list[NormalizedContent], dict]:
        """Collect one batch and return (items, updated_cursor).

        Args:
            cursor: current cursor state
            batch_size: max items to collect this batch

        Returns:
            (list[NormalizedContent], new_cursor)
        """
        phase = cursor.get("phase", "backfill")

        if phase == "backfill":
            return self._collect_backfill_batch(cursor, batch_size)
        else:
            items = self._trending.fetch()
            return items, cursor

    # ------------------------------------------------------------------
    # backfill: 월별 SO API 호출
    # ------------------------------------------------------------------

    def _collect_backfill_batch(
        self, cursor: dict, batch_size: int
    ) -> tuple[list[NormalizedContent], dict]:
        year = cursor.get("year", _BACKFILL_START_YEAR)
        month = cursor.get("month", _BACKFILL_START_MONTH)

        items = self._fetch_month(year, month, batch_size)

        new_cursor = self._advance_cursor(year, month)
        return items, new_cursor

    def _advance_cursor(self, year: int, month: int) -> dict:
        """월 +1. 현재 월을 넘으면 incremental 전환."""
        today = date.today()
        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1

        if (next_year, next_month) > (today.year, today.month):
            logger.info(
                "StackOverflow backfill complete (%d-%02d). → incremental", year, month
            )
            return {"phase": "incremental"}

        return {"phase": "backfill", "year": next_year, "month": next_month}

    def _fetch_month(
        self, year: int, month: int, batch_size: int
    ) -> list[NormalizedContent]:
        """SO API로 특정 월의 hot 질문 수집."""
        last_day = calendar.monthrange(year, month)[1]
        fromdate = int(
            datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()
        )
        todate = int(
            datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc).timestamp()
        )

        params: dict = {
            "order": "desc",
            "sort": "hot",
            "site": _SITE,
            "filter": "withbody",
            "fromdate": fromdate,
            "todate": todate,
            "pagesize": batch_size,
        }
        if self.api_key:
            params["key"] = self.api_key

        try:
            resp = self.session.get(
                f"{_BASE_API_URL}/questions",
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            remaining = data.get("quota_remaining")
            if remaining is not None:
                logger.info("StackOverflow API quota remaining: %d", remaining)

            questions: list[dict] = data.get("items") or []
            if not questions:
                logger.info(
                    "StackOverflow backfill %d-%02d: no questions returned", year, month
                )
                return []

            question_ids = [q["question_id"] for q in questions]
            answers_map = self._trending._fetch_answers_batch(question_ids)

            results: list[NormalizedContent] = []
            for q in questions:
                content = self._api_question_to_normalized(
                    q, answers_map.get(q.get("question_id", 0), [])
                )
                if content:
                    results.append(content)

            logger.info(
                "StackOverflow backfill %d-%02d: collected=%d",
                year,
                month,
                len(results),
            )
            return results

        except Exception:
            logger.exception("StackOverflow backfill %d-%02d fetch failed", year, month)
            return []

    def _api_question_to_normalized(
        self, q: dict, answers: list[dict]
    ) -> NormalizedContent | None:
        canonical_url = q.get("link")
        if not canonical_url:
            return None

        owner = q.get("owner") or {}
        author = owner.get("display_name") or None

        published_at: str | None = None
        creation_date = q.get("creation_date")
        if creation_date is not None:
            published_at = datetime.fromtimestamp(
                creation_date, tz=timezone.utc
            ).isoformat()

        question_body: str | None = q.get("body")

        preview: str | None = None
        if question_body:
            plain = re.sub(r"<[^>]+>", " ", question_body)
            plain = re.sub(r"\s+", " ", plain).strip()
            preview = (
                plain[:_PREVIEW_MAX_LENGTH] + "..."
                if len(plain) > _PREVIEW_MAX_LENGTH
                else plain
            )

        is_answered: bool | None = q.get("is_answered")

        valid_answers = [a for a in answers if a.get("body")]
        accepted_raw = next((a for a in valid_answers if a.get("is_accepted")), None)
        top_raw = sorted(
            (a for a in valid_answers if not a.get("is_accepted")),
            key=lambda a: a.get("score", 0),
            reverse=True,
        )[:_TOP_ANSWER_LIMIT]

        accepted_answer: dict | None = None
        if accepted_raw:
            accepted_answer = {
                "body": accepted_raw.get("body", ""),
                "score": accepted_raw.get("score", 0),
            }

        top_answers: list[dict] = [
            {"body": a.get("body", ""), "score": a.get("score", 0)}
            for a in top_raw
            if a.get("body")
        ]

        merged = _build_body_candidate(
            question_body, accepted_answer, top_answers
        )

        return NormalizedContent(
            source_name="Stack Overflow",
            title=q.get("title"),
            author=author,
            canonical_url=canonical_url,
            published_at=published_at,
            preview=preview,
            body_candidate=None,
            pipeline_body=merged,
            is_original_visible=False,
            license_type=_LICENSE_TYPE,
            view_count=None,
            score=None,
            likes=None,
            is_answered=None,
            question_content=None,
            accepted_answer=None,
            top_answers=[],
        )
