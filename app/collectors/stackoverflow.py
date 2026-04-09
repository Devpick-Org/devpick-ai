"""Stack Overflow Trending page collector (hybrid: HTML scrape + API body fetch).

수집 전략:
- https://stackoverflow.com/questions?tab=trending 크롤링으로 trending 질문 목록 수집
- 수집한 post_id 목록으로 SO API v2.3 batch 호출 → body + answers 가져오기
- acceptedAnswer + score 상위 2개 topAnswers를 별도 구조화 필드로 저장
- 필터링 없음 (score, view_count 필터 제거)
- License: CC BY-SA 4.0
- API 키 없으면 일일 300회, 있으면 10,000회 쿼터
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.schemas.normalized_content import NormalizedContent

logger = logging.getLogger(__name__)

_TRENDING_URL = "https://stackoverflow.com/questions?tab=trending"
_BASE_API_URL = "https://api.stackexchange.com/2.3"
_SITE = "stackoverflow"
_LICENSE_TYPE = "CC BY-SA 4.0"
_TOP_ANSWER_LIMIT = 2
_PREVIEW_MAX_LENGTH = 300
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class StackOverflowCollector:
    """Collects trending Q&A content from Stack Overflow Trending page.

    수집 방식:
    1. https://stackoverflow.com/questions?tab=trending HTML 크롤링
       → post_id, title, url, score, view_count, published_at, preview, tags, author 추출
    2. 수집한 post_id로 SO API batch 호출 → body + answers 가져오기
    3. NormalizedContent 생성 (필터링 없음)

    Usage:
        collector = StackOverflowCollector(api_key="...")
        contents = collector.fetch()
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 15.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key or ""
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

    def fetch(self) -> list[NormalizedContent]:
        """Fetch trending questions from Stack Overflow Trending page."""
        try:
            scraped = self._scrape_trending_page()
            if not scraped:
                logger.info("StackOverflow trending page returned no questions")
                return []

            post_ids = [item["post_id"] for item in scraped]

            bodies_map = self._fetch_bodies_batch(post_ids)

            answered_ids = [
                item["post_id"]
                for item in scraped
                if bodies_map.get(item["post_id"], {}).get("is_answered")
            ]
            answers_map: dict[int, list[dict]] = {}
            if answered_ids:
                answers_map = self._fetch_answers_batch(answered_ids)

            results: list[NormalizedContent] = []
            for item in scraped:
                pid = item["post_id"]
                api_data = bodies_map.get(pid, {})
                content = self._to_normalized_content(
                    item, api_data, answers_map.get(pid, [])
                )
                if content is not None:
                    results.append(content)

            logger.info("StackOverflow trending collected=%d", len(results))
            return results

        except Exception:
            logger.exception("StackOverflow collection failed")
            return []

    # ------------------------------------------------------------------
    # HTML 크롤링
    # ------------------------------------------------------------------

    def _scrape_trending_page(self) -> list[dict]:
        """Scrape https://stackoverflow.com/questions?tab=trending.

        Returns:
            list of dicts with keys:
                post_id, title, canonical_url, score, view_count,
                published_at, preview, author
        """
        resp = self.session.get(
            _TRENDING_URL,
            headers={"User-Agent": _DEFAULT_USER_AGENT},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        html = resp.text

        post_ids = [int(pid) for pid in re.findall(r'data-post-id="(\d+)"', html)]

        title_url_pairs = re.findall(
            r'href="(/questions/\d+/[^"]+)"\s+class="s-link"[^>]*>'
            r'<span itemprop="name">([^<]+)</span>',
            html,
        )

        scores = [
            int(v)
            for v in re.findall(
                r'<span\s[^>]*itemprop="upvoteCount"[^>]*>\s*(-?\d+)\s*</span>',
                html,
            )
        ]

        view_counts = [
            int(v.replace(",", ""))
            for v in re.findall(r'title="([\d,]+)\s+views?"', html)
        ]

        dates = re.findall(r'itemprop="dateCreated"\s+content="([^"]+)"', html)

        previews = [
            p.strip()
            for p in re.findall(
                r'itemprop="text">\s*(.*?)\s*</div>',
                html,
                re.DOTALL,
            )
        ]

        authors = re.findall(
            r'href="/users/\d+/([^"]+)"\s',
            html,
        )

        results: list[dict] = []
        for i, post_id in enumerate(post_ids):
            if i >= len(title_url_pairs):
                break

            url_path, title = title_url_pairs[i]
            canonical_url = f"https://stackoverflow.com{url_path}"

            published_at: str | None = None
            if i < len(dates):
                try:
                    dt = datetime.fromisoformat(dates[i].replace("Z", "+00:00"))
                    published_at = dt.isoformat()
                except (ValueError, AttributeError):
                    pass

            preview: str | None = previews[i].strip() if i < len(previews) else None
            if preview and len(preview) > _PREVIEW_MAX_LENGTH:
                preview = preview[:_PREVIEW_MAX_LENGTH] + "..."

            results.append(
                {
                    "post_id": post_id,
                    "title": title.strip(),
                    "canonical_url": canonical_url,
                    "score": scores[i] if i < len(scores) else None,
                    "view_count": view_counts[i] if i < len(view_counts) else None,
                    "published_at": published_at,
                    "preview": preview,
                    "author": authors[i] if i < len(authors) else None,
                }
            )

        logger.info("StackOverflow trending scrape: %d questions", len(results))
        return results

    # ------------------------------------------------------------------
    # API batch 호출 (body + answers)
    # ------------------------------------------------------------------

    def _fetch_bodies_batch(self, post_ids: list[int]) -> dict[int, dict]:
        """Fetch question bodies + tags + is_answered for given post_ids via SO API."""
        if not post_ids:
            return {}
        ids_str = ";".join(str(pid) for pid in post_ids)
        params: dict = {
            "site": _SITE,
            "filter": "withbody",
            "pagesize": 100,
        }
        if self.api_key:
            params["key"] = self.api_key

        try:
            resp = self.session.get(
                f"{_BASE_API_URL}/questions/{ids_str}",
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            remaining = data.get("quota_remaining")
            if remaining is not None:
                logger.info("StackOverflow API quota remaining: %d", remaining)

            items: list[dict] = data.get("items") or []
            return {item["question_id"]: item for item in items}
        except Exception:
            logger.warning("Failed to fetch question bodies", exc_info=True)
            return {}

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
                f"{_BASE_API_URL}/questions/{ids_str}/answers",
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
            logger.warning("Failed to fetch answers", exc_info=True)
            return {}

    # ------------------------------------------------------------------
    # NormalizedContent 변환
    # ------------------------------------------------------------------

    def _to_normalized_content(
        self,
        scraped: dict,
        api_data: dict,
        answers: list[dict],
    ) -> NormalizedContent | None:
        canonical_url = scraped.get("canonical_url")
        if not canonical_url:
            return None

        # API에서 tags 가져오기 (없으면 빈 리스트)
        tags: list[str] = api_data.get("tags") or []

        # is_answered
        is_answered: bool | None = api_data.get("is_answered")

        # question_content: API body (원문 HTML)
        question_content: str | None = api_data.get("body")

        # accepted_answer + top_answers 구조화
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

        return NormalizedContent(
            source_name="Stack Overflow",
            title=scraped.get("title"),
            author=scraped.get("author"),
            canonical_url=canonical_url,
            published_at=scraped.get("published_at"),
            preview=scraped.get("preview"),
            body_candidate=question_content,  # 본문 호환성 유지
            is_original_visible=True,
            license_type=_LICENSE_TYPE,
            tags=tags,
            view_count=scraped.get("view_count"),
            likes=scraped.get("score"),
            is_answered=is_answered,
            question_content=question_content,
            accepted_answer=accepted_answer,
            top_answers=top_answers,
        )
