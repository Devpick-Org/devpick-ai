"""YouTube Data API v3 기반 영상 수집기 (DP-415).

수집 전략:
- PostgreSQL tags 테이블 키워드를 7일 로테이션으로 나눠 오늘 담당 서브셋만 수집
- search.list(keyword, relevanceLanguage=ko, order=viewCount) → video ID 목록
- videos.list(ids, part=snippet,statistics,contentDetails) → 상세 정보 (50개 배치)
- 품질 필터: viewCount > 5,000 / 좋아요 비율 3%+ / 영상 길이 4~30분
- content_tags 매핑: 제목+설명 ↔ tags 테이블 대소문자 무시 매칭, 없으면 검색 키워드 fallback
"""

from __future__ import annotations

import logging
import re
from datetime import date

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import create_engine, text
from urllib3.util.retry import Retry

from app.schemas.normalized_content import NormalizedContent

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
_MIN_VIEW_COUNT = 5_000
_MIN_LIKE_RATIO = 0.03
_MIN_DURATION_SEC = 240  # 4분
_MAX_DURATION_SEC = 1_800  # 30분
_PREVIEW_MAX_LEN = 260
_SEARCH_MAX_RESULTS = 50
_VIDEOS_BATCH_SIZE = 50
_ROTATION_DAYS = 7
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _parse_duration_seconds(duration: str) -> int:
    m = _DURATION_RE.match(duration)
    if not m:
        return 0
    h, mn, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mn * 60 + s


class YouTubeCollector:
    """YouTube Data API v3 기반 영상 수집기.

    Usage:
        collector = YouTubeCollector(api_key="...", database_url="postgresql://...")
        items = collector.fetch()  # list[NormalizedContent]
    """

    def __init__(
        self,
        api_key: str,
        database_url: str,
        timeout: float = 15.0,
        max_retries: int = 2,
    ) -> None:
        self._api_key = api_key
        self._database_url = database_url
        self._session = self._build_session(timeout, max_retries)

    @staticmethod
    def _build_session(timeout: float, max_retries: int) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.request = lambda method, url, **kw: requests.Session.request(  # type: ignore[method-assign]
            session, method, url, timeout=timeout, **kw
        )
        return session

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def fetch(self) -> list[NormalizedContent]:
        all_tags = self._load_all_tags()
        if not all_tags:
            logger.warning("tags 테이블이 비어 있음 — YouTube 수집 스킵")
            return []

        tag_names = [t["name"] for t in all_tags]
        today_keywords = self._get_todays_keywords(tag_names)
        logger.info("오늘 수집 키워드 %d개: %s", len(today_keywords), today_keywords)

        video_ids: list[str] = []
        keyword_map: dict[str, str] = {}  # video_id → 검색 키워드
        for keyword in today_keywords:
            ids = self._search_video_ids(keyword)
            for vid in ids:
                if vid not in keyword_map:
                    keyword_map[vid] = keyword
            video_ids.extend(ids)

        if not video_ids:
            logger.info("검색 결과 없음")
            return []

        unique_ids = list(dict.fromkeys(video_ids))
        video_details = self._fetch_video_details(unique_ids)
        logger.info("API 응답 영상 수: %d", len(video_details))

        results: list[NormalizedContent] = []
        for video in video_details:
            item = self._to_normalized_content(video, keyword_map, tag_names)
            if item is not None:
                results.append(item)

        logger.info("품질 필터 통과: %d개", len(results))
        return results

    # ------------------------------------------------------------------
    # DB
    # ------------------------------------------------------------------

    def _load_all_tags(self) -> list[dict]:
        engine = create_engine(self._database_url, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT id, name FROM tags ORDER BY name")
                ).fetchall()
            return [{"id": str(r[0]), "name": r[1]} for r in rows]
        finally:
            engine.dispose()

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    @staticmethod
    def _get_todays_keywords(keywords: list[str]) -> list[str]:
        n = len(keywords)
        if n == 0:
            return []
        day = date.today().toordinal() % _ROTATION_DAYS
        chunk = max(1, (n + _ROTATION_DAYS - 1) // _ROTATION_DAYS)
        start = day * chunk
        return keywords[start : start + chunk]

    # ------------------------------------------------------------------
    # YouTube API
    # ------------------------------------------------------------------

    def _search_video_ids(self, keyword: str) -> list[str]:
        try:
            resp = self._session.get(
                _SEARCH_URL,
                params={
                    "part": "id",
                    "q": keyword,
                    "type": "video",
                    "relevanceLanguage": "ko",
                    "order": "viewCount",
                    "maxResults": _SEARCH_MAX_RESULTS,
                    "key": self._api_key,
                },
            )
            resp.raise_for_status()
            return [item["id"]["videoId"] for item in resp.json().get("items", [])]
        except Exception:
            logger.warning("search.list 실패 — keyword=%s", keyword, exc_info=True)
            return []

    def _fetch_video_details(self, video_ids: list[str]) -> list[dict]:
        results: list[dict] = []
        for i in range(0, len(video_ids), _VIDEOS_BATCH_SIZE):
            batch = video_ids[i : i + _VIDEOS_BATCH_SIZE]
            try:
                resp = self._session.get(
                    _VIDEOS_URL,
                    params={
                        "part": "snippet,statistics,contentDetails",
                        "id": ",".join(batch),
                        "key": self._api_key,
                    },
                )
                resp.raise_for_status()
                results.extend(resp.json().get("items", []))
            except Exception:
                logger.warning("videos.list 실패 — ids=%s", batch, exc_info=True)
        return results

    # ------------------------------------------------------------------
    # Quality filter
    # ------------------------------------------------------------------

    def _passes_quality_filter(self, video: dict) -> bool:
        stats = video.get("statistics", {})
        view_count = int(stats.get("viewCount", 0))
        if view_count < _MIN_VIEW_COUNT:
            return False

        duration_str = video.get("contentDetails", {}).get("duration", "PT0S")
        secs = _parse_duration_seconds(duration_str)
        if not (_MIN_DURATION_SEC <= secs <= _MAX_DURATION_SEC):
            return False

        like_count_str = stats.get("likeCount")
        if like_count_str is not None and view_count > 0:
            if int(like_count_str) / view_count < _MIN_LIKE_RATIO:
                return False

        return True

    # ------------------------------------------------------------------
    # Tag mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_tags(video: dict, keyword: str, all_tag_names: list[str]) -> list[str]:
        snippet = video.get("snippet", {})
        text_blob = (
            (snippet.get("title") or "") + " " + (snippet.get("description") or "")
        ).lower()
        matched = [t for t in all_tag_names if t.lower() in text_blob]
        if not matched and keyword in all_tag_names:
            matched = [keyword]
        return matched

    # ------------------------------------------------------------------
    # NormalizedContent 변환
    # ------------------------------------------------------------------

    def _to_normalized_content(
        self,
        video: dict,
        keyword_map: dict[str, str],
        all_tag_names: list[str],
    ) -> NormalizedContent | None:
        if not self._passes_quality_filter(video):
            return None

        video_id = video.get("id", "")
        if not video_id:
            return None

        snippet = video.get("snippet", {})
        stats = video.get("statistics", {})
        content_details = video.get("contentDetails", {})

        title = snippet.get("title") or ""
        channel_name = snippet.get("channelTitle") or ""
        description = snippet.get("description") or ""
        published_at = snippet.get("publishedAt")
        duration = content_details.get("duration", "PT0S")

        thumbnails = snippet.get("thumbnails", {})
        thumbnail_url = (
            (thumbnails.get("maxres") or {}).get("url")
            or (thumbnails.get("high") or {}).get("url")
            or (thumbnails.get("medium") or {}).get("url")
        )

        view_count_str = stats.get("viewCount")
        view_count = int(view_count_str) if view_count_str else None

        keyword = keyword_map.get(video_id, "")
        tags = self._map_tags(video, keyword, all_tag_names)

        return NormalizedContent(
            source_name="YouTube",
            title=title,
            author=channel_name,
            canonical_url=f"https://www.youtube.com/watch?v={video_id}",
            published_at=published_at,
            preview=description[:_PREVIEW_MAX_LEN] if description else None,
            body_candidate=None,
            is_original_visible=True,
            thumbnail_url=thumbnail_url,
            view_count=view_count,
            extra={
                "videoId": video_id,
                "channelName": channel_name,
                "duration": duration,
            },
            content_tags=tags,
        )
