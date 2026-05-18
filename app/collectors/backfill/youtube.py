"""YouTube 채널 기반 영상 수집기.

수집 전략:
- 고정 채널 목록에서 최신 영상 수집 (channels.list → playlistItems.list → videos.list)
- 품질 필터 없음 (큐레이션된 개발 채널이므로 전체 수집)
- content_tags 매핑: 제목+설명 ↔ tags 테이블 대소문자 무시 매칭
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import create_engine, text
from urllib3.util.retry import Retry

from app.schemas.normalized_content import NormalizedContent

logger = logging.getLogger(__name__)

_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
_VIDEOS_BATCH_SIZE = 50
_PREVIEW_MAX_LEN = 260

_VIDEOS_PER_CHANNEL = 10
_MAX_AGE_DAYS = 365  # 1년 이내 영상만 수집

# 한국어 제목 영상에서 영어 태그를 매칭하기 위한 동의어 사전
# key: tags 테이블의 태그명 소문자, value: 한국어/변형 표현 목록
KOREAN_SYNONYMS: dict[str, list[str]] = {
    "spring boot": ["스프링부트", "스프링 부트", "스프링"],
    "spring": ["스프링"],
    "react": ["리액트"],
    "typescript": ["타입스크립트"],
    "javascript": ["자바스크립트"],
    "python": ["파이썬"],
    "java": ["자바"],
    "kotlin": ["코틀린"],
    "kubernetes": ["쿠버네티스", "k8s"],
    "docker": ["도커"],
    "aws": ["아마존", "아마존 웹 서비스"],
    "git": ["깃"],
    "github": ["깃허브"],
    "ci/cd": ["배포 자동화", "깃허브 액션", "github actions"],
    "redis": ["레디스"],
    "next.js": ["넥스트", "넥스트js", "nextjs"],
    "node.js": ["노드", "노드js", "nodejs"],
    "mysql": ["마이에스큐엘", "마이sql"],
    "mongodb": ["몽고db", "몽고디비"],
    "postgresql": ["포스트그레스", "postgres"],
    "algorithm": ["알고리즘"],
    "data structure": ["자료구조"],
    "rust": ["러스트"],
    "go": ["고언어", "golang"],
    "security": ["보안"],
    "caching": ["캐싱", "캐시"],
    "clean code": ["클린 코드", "클린코드"],
    "testing": ["테스트", "테스팅"],
    "debugging": ["디버깅", "디버그"],
    "open source": ["오픈소스"],
    "code review": ["코드리뷰", "코드 리뷰"],
    "backend": ["백엔드"],
    "frontend": ["프론트엔드", "프론트"],
    "database": ["데이터베이스", "데이터 베이스"],
    "api": ["에이피아이"],
    "msa": ["마이크로서비스", "마이크로 서비스"],
}

_CHANNEL_LIST = [
    {"id": "UCSLrpBAzr-ROVGHQ5EmxnUg", "name": "코딩애플"},
    {"id": "UC_4u-bXaba7yrRz_6x6kb_w", "name": "드림코딩"},
    {"id": "UC2nkWbaJt1KQDi2r2XclzTQ", "name": "얄팍한코딩사전"},
    {"id": "UCQNE2JmbasNYbjGAcuBiRRg", "name": "조코딩"},
    {"id": "UCFY_Zc7Hdb5lHGPFmKywXCw", "name": "컴공선배"},
    {"id": "UCvc8kv-i5fvFTJBFAk6n1SA", "name": "생활코딩"},
    {"id": "UCbMGBIayK26L4VaFrs5jyBw", "name": "개발하는남자"},
    {"id": "UCUpJs89fSBXNolQGOYKn0YQ", "name": "노마드코더"},
    {"id": "UC-mOekGSesms0agFntnQang", "name": "우아한Tech"},
    {"id": "UCNrehnUq7Il-J7HQxrzp7CA", "name": "NAVER D2"},
    {"id": "UCReNwSTQ1RqDZDnG9Qz_gyg", "name": "쉬운코드"},
    {"id": "UCVrhnbfe78ODeQglXtT1Elw", "name": "메타코딩"},
    {"id": "UC7iAOLiALt2rtMVAWWl4pnw", "name": "나도코딩"},
    {"id": "UCdGTtaI-ERLjzZNLuBj3X6A", "name": "널널한 개발자 TV"},
    {"id": "UC0Y0T9JpgIBbyGDjvy9PbOg", "name": "인프런"},
    {"id": "UCFDbz39kFPvU0AUpgHx4ICw", "name": "김버그"},
]


def _parse_duration_seconds(duration: str) -> int:
    """ISO 8601 duration 문자열을 초로 변환 (예: PT1M30S → 90)."""
    match = re.fullmatch(
        r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or ""
    )
    if not match:
        return 0
    days, hours, minutes, seconds = (int(v or 0) for v in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


class YouTubeCollector:
    """YouTube 채널 기반 영상 수집기.

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
        tag_names = [t["name"] for t in all_tags]

        video_ids: list[str] = []
        channel_map: dict[str, str] = {}  # video_id → channel name

        for channel in _CHANNEL_LIST:
            playlist_id = self._get_uploads_playlist_id(channel["id"])
            if not playlist_id:
                continue
            ids = self._fetch_playlist_video_ids(playlist_id, _VIDEOS_PER_CHANNEL)
            for vid in ids:
                if vid not in channel_map:
                    channel_map[vid] = channel["name"]
            video_ids.extend(ids)

        if not video_ids:
            logger.info("수집된 영상 없음")
            return []

        unique_ids = list(dict.fromkeys(video_ids))
        video_details = self._fetch_video_details(unique_ids)
        logger.info("API 응답 영상 수: %d", len(video_details))

        results: list[NormalizedContent] = []
        for video in video_details:
            item = self._to_normalized_content(video, channel_map, tag_names)
            if item is not None:
                results.append(item)

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
    # YouTube API
    # ------------------------------------------------------------------

    def _get_uploads_playlist_id(self, channel_id: str) -> str | None:
        try:
            resp = self._session.get(
                _CHANNELS_URL,
                params={
                    "part": "contentDetails",
                    "id": channel_id,
                    "key": self._api_key,
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                logger.warning("채널 정보 없음 — channel_id=%s", channel_id)
                return None
            return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        except Exception:
            logger.warning(
                "channels.list 실패 — channel_id=%s", channel_id, exc_info=True
            )
            return None

    def _fetch_playlist_video_ids(
        self, playlist_id: str, max_results: int
    ) -> list[str]:
        try:
            resp = self._session.get(
                _PLAYLIST_ITEMS_URL,
                params={
                    "part": "contentDetails",
                    "playlistId": playlist_id,
                    "maxResults": max_results,
                    "key": self._api_key,
                },
            )
            resp.raise_for_status()
            return [
                item["contentDetails"]["videoId"]
                for item in resp.json().get("items", [])
            ]
        except Exception:
            logger.warning(
                "playlistItems.list 실패 — playlist_id=%s", playlist_id, exc_info=True
            )
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
    # Tag mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_tags(video: dict, all_tag_names: list[str]) -> list[str]:
        snippet = video.get("snippet", {})
        text_blob = (
            (snippet.get("title") or "") + " " + (snippet.get("description") or "")
        ).lower()
        yt_tags = [t.lower() for t in (snippet.get("tags") or [])]
        matched = []
        for t in all_tag_names:
            t_lower = t.lower()
            pat = re.compile(r"\b" + re.escape(t_lower) + r"\b")
            if pat.search(text_blob) or any(pat.search(st) for st in yt_tags):
                matched.append(t)
                continue
            synonyms = KOREAN_SYNONYMS.get(t_lower, [])
            if any(syn in text_blob for syn in synonyms):
                matched.append(t)
        return matched

    # ------------------------------------------------------------------
    # NormalizedContent 변환
    # ------------------------------------------------------------------

    def _to_normalized_content(
        self,
        video: dict,
        channel_map: dict[str, str],
        all_tag_names: list[str],
    ) -> NormalizedContent | None:
        video_id = video.get("id", "")
        if not video_id:
            return None

        snippet = video.get("snippet", {})
        published_at_str = snippet.get("publishedAt")
        if published_at_str:
            try:
                published_dt = datetime.fromisoformat(
                    published_at_str.replace("Z", "+00:00")
                )
                cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_MAX_AGE_DAYS)
                if published_dt < cutoff:
                    return None
            except ValueError:
                pass
        stats = video.get("statistics", {})
        content_details = video.get("contentDetails", {})

        title = snippet.get("title") or ""
        channel_name = channel_map.get(video_id) or snippet.get("channelTitle") or ""
        description = snippet.get("description") or ""
        duration = content_details.get("duration", "PT0S")

        if _parse_duration_seconds(duration) <= 60:
            return None

        thumbnails = snippet.get("thumbnails", {})
        thumbnail_url = (
            (thumbnails.get("maxres") or {}).get("url")
            or (thumbnails.get("high") or {}).get("url")
            or (thumbnails.get("medium") or {}).get("url")
        )

        view_count_str = stats.get("viewCount")
        view_count = int(view_count_str) if view_count_str else None

        tags = self._map_tags(video, all_tag_names)

        return NormalizedContent(
            source_name="YouTube",
            title=title,
            author=channel_name,
            canonical_url=f"https://www.youtube.com/watch?v={video_id}",
            published_at=published_at_str,
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
