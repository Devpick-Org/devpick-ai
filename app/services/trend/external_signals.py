"""외부 트렌드 시그널 수집 — GitHub Trending / HN Algolia / dev.to (DP-382)."""

from __future__ import annotations

import logging
import math
import time

import requests
from bs4 import BeautifulSoup

from app.services.trend.normalize import TagNormalizer

logger = logging.getLogger(__name__)

_UNIT_SINCE: dict[str, str] = {
    "daily": "daily",
    "weekly": "weekly",
    "monthly": "monthly",
}
_UNIT_TOP: dict[str, int] = {"daily": 1, "weekly": 7, "monthly": 30}
_UNIT_TS_DELTA: dict[str, int] = {
    "daily": 86400,
    "weekly": 604800,
    "monthly": 2592000,
}
_UNIT_MIN_POINTS: dict[str, int] = {"daily": 30, "weekly": 50, "monthly": 100}

_TECH_KEYWORDS: frozenset[str] = frozenset(
    {
        "python",
        "javascript",
        "typescript",
        "rust",
        "go",
        "golang",
        "java",
        "kotlin",
        "swift",
        "cpp",
        "c++",
        "csharp",
        "c#",
        "ruby",
        "php",
        "scala",
        "elixir",
        "haskell",
        "react",
        "vue",
        "angular",
        "nextjs",
        "svelte",
        "astro",
        "remix",
        "nuxt",
        "flutter",
        "react native",
        "docker",
        "kubernetes",
        "k8s",
        "terraform",
        "ansible",
        "aws",
        "gcp",
        "azure",
        "linux",
        "nginx",
        "redis",
        "postgresql",
        "mysql",
        "mongodb",
        "sqlite",
        "graphql",
        "grpc",
        "wasm",
        "webassembly",
        "llm",
        "ai",
        "ml",
        "gpt",
        "claude",
        "gemini",
        "langchain",
        "pytorch",
        "tensorflow",
        "git",
        "github",
        "cicd",
    }
)


def _normalize_scores(signals: dict[str, float]) -> dict[str, float]:
    if not signals:
        return {}
    max_v = max(signals.values())
    if max_v == 0:
        return {}
    return {k: v / max_v for k, v in signals.items()}


class GitHubTrendingFetcher:
    """GitHub Trending HTML 스크래핑으로 언어 태그 시그널을 수집한다."""

    _URL = "https://github.com/trending"
    _TIMEOUT = 10.0

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

    def fetch(self, unit: str) -> dict[str, float]:
        since = _UNIT_SINCE.get(unit, "daily")
        try:
            resp = self._session.get(
                self._URL, params={"since": since}, timeout=self._TIMEOUT
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("GitHub Trending 조회 실패: %s", exc)
            return {}
        return _normalize_scores(self._parse(resp.text))

    def _parse(self, html: str) -> dict[str, float]:
        soup = BeautifulSoup(html, "lxml")
        counts: dict[str, float] = {}
        for article in soup.select("article.Box-row"):
            lang_el = article.select_one("[itemprop='programmingLanguage']")
            if lang_el:
                lang = lang_el.get_text(strip=True).lower()
                if lang:
                    counts[lang] = counts.get(lang, 0) + 1.0
        return counts


class HackerNewsFetcher:
    """HN Algolia API로 points/age 기반 기술 키워드 시그널을 수집한다."""

    _URL = "https://hn.algolia.com/api/v1/search_by_date"
    _TIMEOUT = 10.0

    def fetch(self, unit: str) -> dict[str, float]:
        ts_delta = _UNIT_TS_DELTA.get(unit, 86400)
        min_points = _UNIT_MIN_POINTS.get(unit, 30)
        since_ts = int(time.time()) - ts_delta
        try:
            resp = requests.get(
                self._URL,
                params={
                    "tags": "story",
                    "numericFilters": f"created_at_i>{since_ts},points>{min_points}",
                    "hitsPerPage": 100,
                },
                timeout=self._TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("HN Algolia 조회 실패: %s", exc)
            return {}
        return _normalize_scores(self._parse(resp.json()))

    def _parse(self, data: dict) -> dict[str, float]:
        scores: dict[str, float] = {}
        for hit in data.get("hits", []):
            title = hit.get("title", "").lower()
            points = hit.get("points") or 0
            hit_score = math.floor(math.log2(max(points, 2)))
            for kw in _TECH_KEYWORDS:
                if kw in title:
                    scores[kw] = scores.get(kw, 0) + hit_score
        return scores


class DevToFetcher:
    """dev.to REST API로 period별 인기 글의 태그 시그널을 수집한다."""

    _URL = "https://dev.to/api/articles"
    _TIMEOUT = 10.0

    def fetch(self, unit: str) -> dict[str, float]:
        top = _UNIT_TOP.get(unit, 1)
        try:
            resp = requests.get(
                self._URL,
                params={"per_page": 100, "top": top},
                timeout=self._TIMEOUT,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("dev.to API 조회 실패: %s", exc)
            return {}
        return _normalize_scores(self._parse(resp.json()))

    def _parse(self, articles: list) -> dict[str, float]:
        scores: dict[str, float] = {}
        for article in articles:
            reactions = article.get("public_reactions_count") or 0
            score = 1.0 + math.log1p(reactions) * 0.05
            for tag in article.get("tag_list") or []:
                tag = tag.lower().strip()
                if tag:
                    scores[tag] = scores.get(tag, 0) + score
        return scores


class ExternalSignalFetcher:
    """GitHub Trending / HN Algolia / dev.to 시그널을 블렌딩해 반환한다.

    각 소스는 독립 try/except — 최대 2개 실패해도 나머지 1개로 시그널 유지.
    전체 실패 시 빈 dict 반환 → 오케스트레이터가 내부 데이터만으로 랭킹.
    """

    _WEIGHTS = (
        ("github", 0.35),
        ("hn", 0.35),
        ("devto", 0.30),
    )

    def __init__(self) -> None:
        self._normalizer = TagNormalizer()
        self._fetchers: dict[
            str, GitHubTrendingFetcher | HackerNewsFetcher | DevToFetcher
        ] = {
            "github": GitHubTrendingFetcher(),
            "hn": HackerNewsFetcher(),
            "devto": DevToFetcher(),
        }

    def fetch(self, unit: str) -> dict[str, float]:
        """unit 기준 외부 시그널을 블렌딩해서 반환한다."""
        raw: dict[str, float] = {}
        for name, weight in self._WEIGHTS:
            fetcher = self._fetchers[name]
            try:
                signals = fetcher.fetch(unit)
                for tag, score in signals.items():
                    raw[tag] = raw.get(tag, 0) + score * weight
            except Exception as exc:
                logger.warning("%s 시그널 집계 실패 — skip: %s", name, exc)

        if not raw:
            return {}

        # TagNormalizer로 키 정규화 (동의어 통합, max score 유지)
        tags = list(raw.keys())
        normalized_keys = self._normalizer.normalize(tags)
        result: dict[str, float] = {}
        for orig, norm in zip(tags, normalized_keys):
            result[norm] = max(result.get(norm, 0.0), raw[orig])
        return result
