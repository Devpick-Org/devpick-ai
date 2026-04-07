"""Stack Overflow API v2.3 collector for Q&A content.

수집 전략:
- sort=hot — 최신 + 높은 점수 가중 (score / (age_hours+1)^1.5)
- fromdate=7일 전 — 최근 1주 이내 게시물만 (트렌딩 포커스)
- pagesize=30 — 후보 풀 확보 후 임계값 필터링
- min=5 — 추천수(score) 5 이상인 질문만
- view_count >= 500 — 조회수 500 이상 (수집 후 필터링)
- answered 질문에 한해 배치로 답변 수집 (1회 API 호출)
- acceptedAnswer + score 상위 2개 topAnswers를 body_candidate에 통합
- License: CC BY-SA 4.0 (저자명 + 원문 링크 표시 조건으로 원문 표시 허용)
- API 키 없으면 일일 300회, 있으면 10,000회 쿼터
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.schemas.normalized_content import NormalizedContent

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.stackexchange.com/2.3"
_SITE = "stackoverflow"
_LICENSE_TYPE = "CC BY-SA 4.0"
_PAGE_SIZE = 30
_TOP_ANSWER_LIMIT = 2
_PREVIEW_MAX_LENGTH = 300
_DEFAULT_DAYS_BACK = 7
_DEFAULT_MIN_SCORE = 5
_DEFAULT_MIN_VIEWS = 500


class StackOverflowCollector:
    """Collects trending Q&A content from Stack Overflow API v2.3.

    수집 기준:
    - sort=hot (시간 가중 인기도), 7일 이내
    - score >= min_score (기본 5)
    - view_count >= min_views (기본 500, 수집 후 필터링)

    Usage:
        collector = StackOverflowCollector(api_key="...", min_score=5, min_views=500)
        contents = collector.fetch(tags=["java", "python"])
        # contents: list[NormalizedContent]
    """

    def __init__(
        self,
        api_key: str | None = None,
        min_score: int = _DEFAULT_MIN_SCORE,
        min_views: int = _DEFAULT_MIN_VIEWS,
        days_back: int = _DEFAULT_DAYS_BACK,
        timeout: float = 15.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key or ""
        self.min_score = min_score
        self.min_views = min_views
        self.days_back = days_back
        self.timeout = timeout
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

    def fetch(self, tags: list[str]) -> list[NormalizedContent]:
        """Fetch trending questions with answers from Stack Overflow API.

        Args:
            tags: Tag filters (e.g. ["java", "spring-boot"]).

        Returns:
            List of NormalizedContent after applying score/view thresholds.
        """
        try:
            questions = self._fetch_questions(tags)
            if not questions:
                logger.info("StackOverflow returned no questions for tags=%s", tags)
                return []

            # view_count 임계값 필터링 (API 파라미터 미지원)
            filtered = [
                q for q in questions if (q.get("view_count") or 0) >= self.min_views
            ]
            if not filtered:
                logger.info(
                    "StackOverflow all %d questions filtered out (view_count<%d)",
                    len(questions),
                    self.min_views,
                )
                return []

            logger.info(
                "StackOverflow questions: fetched=%d, after_view_filter=%d",
                len(questions),
                len(filtered),
            )

            answered_ids = [q["question_id"] for q in filtered if q.get("is_answered")]
            answers_map: dict[int, list[dict]] = {}
            if answered_ids:
                answers_map = self._fetch_answers_batch(answered_ids)

            results: list[NormalizedContent] = []
            for q in filtered:
                content = self._to_normalized_content(
                    q, answers_map.get(q.get("question_id", 0), [])
                )
                if content is not None:
                    results.append(content)

            logger.info(
                "StackOverflow collected=%d tags=%s score>=%d views>=%d",
                len(results),
                tags,
                self.min_score,
                self.min_views,
            )
            return results

        except Exception:
            logger.exception("StackOverflow collection failed tags=%s", tags)
            return []

    def _fetch_questions(self, tags: list[str]) -> list[dict]:
        from_date = int(
            (datetime.now(timezone.utc) - timedelta(days=self.days_back)).timestamp()
        )
        params: dict = {
            "order": "desc",
            "sort": "hot",  # 변경: votes → hot (시간 가중 인기도)
            "site": _SITE,
            "filter": "withbody",
            "fromdate": from_date,
            "pagesize": _PAGE_SIZE,
            "min": self.min_score,  # score 최솟값 서버측 필터링
        }
        if tags:
            params["tagged"] = ";".join(tags)
        if self.api_key:
            params["key"] = self.api_key

        resp = self.session.get(
            f"{_BASE_URL}/questions",
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        remaining = data.get("quota_remaining")
        if remaining is not None:
            logger.info("StackOverflow API quota remaining: %d", remaining)

        return data.get("items") or []

    def _fetch_answers_batch(self, question_ids: list[int]) -> dict[int, list[dict]]:
        """Fetch all answers for multiple questions in a single API call."""
        ids_str = ";".join(str(qid) for qid in question_ids)
        params: dict = {
            "order": "desc",
            "sort": "votes",
            "site": _SITE,
            "filter": "withbody",
            "pagesize": 100,
        }
        if self.api_key:
            params["key"] = self.api_key

        try:
            resp = self.session.get(
                f"{_BASE_URL}/questions/{ids_str}/answers",
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            items: list[dict] = resp.json().get("items") or []

            answers_map: dict[int, list[dict]] = {}
            for answer in items:
                qid = answer.get("question_id")
                if qid is not None:
                    answers_map.setdefault(qid, []).append(answer)
            return answers_map

        except Exception:
            logger.warning(
                "Failed to fetch answers for question_ids=%s",
                question_ids,
                exc_info=True,
            )
            return {}

    def _to_normalized_content(
        self, q: dict, answers: list[dict]
    ) -> NormalizedContent | None:
        canonical_url = q.get("link")
        if not canonical_url:
            return None

        owner = q.get("owner") or {}
        author = owner.get("display_name") or "Unknown"

        body = q.get("body")
        preview: str | None = None
        if body:
            preview = (
                body[:_PREVIEW_MAX_LENGTH] + "..."
                if len(body) > _PREVIEW_MAX_LENGTH
                else body
            )

        published_at: str | None = None
        creation_date = q.get("creation_date")
        if creation_date is not None:
            published_at = datetime.fromtimestamp(
                creation_date, tz=timezone.utc
            ).isoformat()

        valid_answers = [a for a in answers if a.get("body")]
        accepted = next((a for a in valid_answers if a.get("is_accepted")), None)
        top_answers = sorted(
            (a for a in valid_answers if not a.get("is_accepted")),
            key=lambda a: a.get("score", 0),
            reverse=True,
        )[:_TOP_ANSWER_LIMIT]

        body_candidate = _build_body_candidate(body, accepted, top_answers)

        return NormalizedContent(
            source_name="Stack Overflow",
            title=q.get("title"),
            author=author,
            canonical_url=canonical_url,
            published_at=published_at,
            preview=preview,
            body_candidate=body_candidate,
            is_original_visible=True,
            license_type=_LICENSE_TYPE,
            tags=q.get("tags") or [],
            view_count=q.get("view_count"),
            likes=q.get("score"),
        )


def _build_body_candidate(
    question_body: str | None,
    accepted_answer: dict | None,
    top_answers: list[dict],
) -> str | None:
    """Combine question body and answers into a single AI-ready text block."""
    if not question_body and not accepted_answer and not top_answers:
        return None

    parts: list[str] = []
    if question_body:
        parts.append(f"## Question\n{question_body}")
    if accepted_answer and accepted_answer.get("body"):
        parts.append(f"## Accepted Answer\n{accepted_answer['body']}")
    if top_answers:
        top_bodies = "\n\n".join(a["body"] for a in top_answers if a.get("body"))
        if top_bodies:
            parts.append(f"## Top Answers\n{top_bodies}")

    result = "\n\n".join(parts).strip()
    return result or None
