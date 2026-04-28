"""외부 트렌드 시그널 수집 — GitHub Trending / HN Algolia / dev.to (DP-382)."""

from __future__ import annotations

import logging
import math
import re
import time

import requests
from bs4 import BeautifulSoup

from app.services.trend.normalize import TagNormalizer

logger = logging.getLogger(__name__)

# ── 단위별 파라미터 ────────────────────────────────────────────────────────────

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

# ── 키워드 / 필터 상수 ─────────────────────────────────────────────────────────

# 기술 키워드 기본 세트 — HN·GitHub description 매칭 anchor 시드.
# _extended_keywords()에서 내부 태그 vocab과 합산하여 자동 확장된다.
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
        # 신생 기술 보강
        "bun",
        "deno",
        "biome",
        "tauri",
        "htmx",
        "elysia",
        "hono",
        "vite",
        "vitest",
        "pnpm",
        "turborepo",
        "ollama",
        "huggingface",
        "openai",
        "mistral",
        "fastapi",
        "django",
        "flask",
        "express",
        "nestjs",
        "springboot",
        "kafka",
        "rabbitmq",
        "elasticsearch",
        "wsl",
        "podman",
        "helm",
        "solidity",
        "web3",
        "blockchain",
        "zig",
        "gleam",
        "ocaml",
        "clojure",
        "dart",
        "spark",
        "dbt",
        "airflow",
        "mlflow",
        "cassandra",
        "dynamodb",
        "supabase",
        "prisma",
        "drizzle",
    }
)

# dev.to 메타/커뮤니티 태그 차단 목록 — tech 시그널과 무관한 태그를 제거한다.
_DEVTO_DENYLIST: frozenset[str] = frozenset(
    {
        "discuss",
        "watercooler",
        "devchallenge",
        "weekendchallenge",
        "challenge",
        "showdev",
        "explainlikeimfive",
        "eli5",
        "rant",
        "career",
        "motivation",
        "productivity",
        "todayilearned",
        "til",
        "news",
        "help",
        "advice",
        "meta",
        "joke",
        "meme",
        "tutorial",
        "beginners",
        "learning",
    }
)

# HN 제목·GitHub description 토큰화 시 제외할 영어 불용어.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "up",
        "about",
        "into",
        "through",
        "during",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "we",
        "you",
        "they",
        "he",
        "she",
        "who",
        "what",
        "which",
        "how",
        "why",
        "when",
        "where",
        "i",
        "my",
        "your",
        "our",
        "new",
        "best",
        "top",
        "vs",
        "v2",
        "show",
        "ask",
        "tell",
        "open",
        "run",
    }
)

# 출력 스케일 — ranking.py 내부 점수 최대 ~4.0 대비 ~50% 영향력.
# 전체 소스 합의(모든 소스에서 1위) 시 이 값이 최댓값이 된다.
_EXTERNAL_SCALE: float = 2.0


def _normalize_scores(signals: dict[str, float]) -> dict[str, float]:
    if not signals:
        return {}
    max_v = max(signals.values())
    if max_v == 0:
        return {}
    return {k: v / max_v for k, v in signals.items()}


def _extended_keywords(internal_tags: set[str] | None) -> frozenset[str]:
    """_TECH_KEYWORDS에 내부 태그 vocab을 합산해 확장 키워드 세트를 반환한다.

    internal_tags: 오케스트레이터에서 주입한 직전 기간 정규화 태그 집합.
    ASCII 2자 이상 불용어 아닌 태그만 포함해 노이즈를 통제한다.
    """
    if not internal_tags:
        return _TECH_KEYWORDS
    extra = frozenset(
        t
        for t in internal_tags
        if len(t) >= 2 and t.lower() not in _STOPWORDS and t.isascii()
    )
    return _TECH_KEYWORDS | extra


def _word_match(kw: str, text: str) -> bool:
    """키워드가 텍스트에서 독립 단어로 매칭되는지 확인한다.

    c++, c#, next.js 같이 특수 문자 포함 키워드는 앞뒤
    영숫자 비존재 조건으로 처리한다.
    """
    if re.search(r"[+#.]", kw):
        return bool(
            re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", text)
        )
    return bool(re.search(r"\b" + re.escape(kw) + r"\b", text))


class GitHubTrendingFetcher:
    """GitHub Trending HTML 스크래핑으로 언어 태그 + 설명 키워드 시그널을 수집한다."""

    _URL = "https://github.com/trending"
    _TIMEOUT = 10.0

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

    def fetch(
        self,
        unit: str,
        extended_keywords: frozenset[str] | None = None,
    ) -> dict[str, float]:
        since = _UNIT_SINCE.get(unit, "daily")
        try:
            resp = self._session.get(
                self._URL, params={"since": since}, timeout=self._TIMEOUT
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("GitHub Trending 조회 실패: %s", exc)
            return {}
        return _normalize_scores(
            self._parse(resp.text, extended_keywords or _TECH_KEYWORDS)
        )

    def _parse(self, html: str, extended_keywords: frozenset[str]) -> dict[str, float]:
        soup = BeautifulSoup(html, "lxml")
        counts: dict[str, float] = {}
        for article in soup.select("article.Box-row"):
            # 1) 프로그래밍 언어 칩 (weight 1.0)
            lang_el = article.select_one("[itemprop='programmingLanguage']")
            if lang_el:
                lang = lang_el.get_text(strip=True).lower()
                if lang:
                    counts[lang] = counts.get(lang, 0) + 1.0

            # 2) repo 이름 + description 에서 확장 키워드 매칭 (weight 0.5)
            repo_el = article.select_one("h2 a")
            desc_el = article.select_one("p")
            text = " ".join(
                filter(
                    None,
                    [
                        repo_el.get_text(strip=True) if repo_el else "",
                        desc_el.get_text(strip=True) if desc_el else "",
                    ],
                )
            ).lower()
            if text:
                for kw in extended_keywords:
                    if _word_match(kw, text):
                        counts[kw] = counts.get(kw, 0) + 0.5
        return counts


class HackerNewsFetcher:
    """HN Algolia API로 points/age 기반 기술 키워드 시그널을 수집한다."""

    _URL = "https://hn.algolia.com/api/v1/search_by_date"
    _TIMEOUT = 10.0

    def fetch(
        self,
        unit: str,
        extended_keywords: frozenset[str] | None = None,
    ) -> dict[str, float]:
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
        return _normalize_scores(
            self._parse(resp.json(), extended_keywords or _TECH_KEYWORDS)
        )

    def _parse(self, data: dict, extended_keywords: frozenset[str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for hit in data.get("hits", []):
            title = hit.get("title", "").lower()
            points = hit.get("points") or 0
            hit_score = math.floor(math.log2(max(points, 2)))
            for kw in extended_keywords:
                if _word_match(kw, title):
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
                if not tag or len(tag) < 2:
                    continue
                if tag in _DEVTO_DENYLIST or tag in _STOPWORDS:
                    continue
                scores[tag] = scores.get(tag, 0) + score
        return scores


class ExternalSignalFetcher:
    """GitHub Trending / HN Algolia / dev.to 시그널을 블렌딩해 반환한다.

    각 소스는 독립 try/except — 최대 2개 실패해도 나머지 1개로 시그널 유지.
    전체 실패 시 빈 dict 반환 → 오케스트레이터가 내부 데이터만으로 랭킹.
    출력 값 범위: [0, _EXTERNAL_SCALE] — ranking.py 내부 점수 최대 ~4.0의 ~50%.
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

    def fetch(
        self,
        unit: str,
        internal_tags: set[str] | None = None,
    ) -> dict[str, float]:
        """unit 기준 외부 시그널을 블렌딩해서 반환한다.

        internal_tags: 오케스트레이터에서 주입하는 직전 기간 정규화 태그 집합.
        HN / GitHub description 키워드 매칭 범위를 확장하는 데 사용된다.
        """
        ext_kw = _extended_keywords(internal_tags)
        raw: dict[str, float] = {}
        for name, weight in self._WEIGHTS:
            fetcher = self._fetchers[name]
            try:
                if name in ("github", "hn"):
                    signals = fetcher.fetch(unit, extended_keywords=ext_kw)
                else:
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

        # 출력 스케일 적용 — 전체 합의 시 최댓값 _EXTERNAL_SCALE
        return {k: v * _EXTERNAL_SCALE for k, v in result.items()}
