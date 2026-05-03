"""YouTube 채널 기반 영상 수집기.

수집 전략:
- 고정 채널 목록에서 최신 영상 수집 (channels.list → playlistItems.list → videos.list)
- 품질 필터 없음 (큐레이션된 개발 채널이므로 전체 수집)
- content_tags 매핑: 제목+설명 ↔ tags 테이블 대소문자 무시 매칭
"""

from __future__ import annotations

import logging

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

# TODO: 테스트용 — 채널당 1개만 수집. 운영 시 10으로 변경
_VIDEOS_PER_CHANNEL = 1

_CHANNEL_LIST = [
    # 국내
    {"id": "UCSLrpBAzr-ROVGHQ5EmxnUg", "name": "코딩애플"},
    {"id": "UC_4u-bXaba7yrRz_6x6kb_w", "name": "드림코딩"},
    {"id": "UC2nkWbaJt1KQDi2r2XclzTQ", "name": "얄팍한코딩사전"},
    {"id": "UCQNE2JmbasNYbjGAcuBiRRg", "name": "조코딩"},
    {"id": "UCFY_Zc7Hdb5lHGPFmKywXCw", "name": "컴공선배"},
    {"id": "UCvc8kv-i5fvFTJBFAk6n1SA", "name": "생활코딩"},
    {"id": "UCbMGBIayK26L4VaFrs5jyBw", "name": "개발하는남자"},
    {"id": "UCUpJs89fSBXNolQGOYKn0YQ", "name": "노마드코더"},
    # 해외
    {"id": "UCsBjURrPoezykLs9EqgamOA", "name": "Fireship"},
    {"id": "UCZgt6AzoyjslHTC9dz0UoTw", "name": "ByteByteGo"},
    {"id": "UC8butISFwT-Wl7EV0hUK0BQ", "name": "freeCodeCamp"},
    {"id": "UC29ju8bIPH5as8OGnQzwJyA", "name": "Traversy Media"},
    {"id": "UCFbNIlppjAuEX4znoulh0Cw", "name": "Web Dev Simplified"},
    {"id": "UCdngmbVKX1Tgre699-XLlUA", "name": "TechWorld with Nana"},
    {"id": "UCbRP3c757lWg9M-U7TyEkXA", "name": "Theo (t3.gg)"},
    {"id": "UC8ENHE5xdFSwx71u3fDH5Xw", "name": "ThePrimeagen"},
    {"id": "UC9x0AN7BWHpCDHSm9NiJFJQ", "name": "NetworkChuck"},
    {"id": "UC_ML5xP23TOWKUcc-oAE_Eg", "name": "Hussein Nasser"},
]


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
        return [t for t in all_tag_names if t.lower() in text_blob]

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
        stats = video.get("statistics", {})
        content_details = video.get("contentDetails", {})

        title = snippet.get("title") or ""
        channel_name = channel_map.get(video_id) or snippet.get("channelTitle") or ""
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

        tags = self._map_tags(video, all_tag_names)

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
