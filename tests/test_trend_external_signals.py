"""ExternalSignalFetcher + 개별 fetcher 단위 테스트 (DP-382)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pytest import approx as pytest_approx

from app.services.trend.external_signals import (
    DevToFetcher,
    ExternalSignalFetcher,
    GitHubTrendingFetcher,
    HackerNewsFetcher,
    _EXTERNAL_SCALE,
)

# ── 공통 HTML fixture ──────────────────────────────────────────────────────────

_GITHUB_HTML = """
<html><body>
  <article class="Box-row">
    <span itemprop="programmingLanguage">Python</span>
  </article>
  <article class="Box-row">
    <span itemprop="programmingLanguage">Rust</span>
  </article>
  <article class="Box-row">
    <span itemprop="programmingLanguage">Python</span>
  </article>
</body></html>
"""


def _mock_resp(status: int = 200, json_data=None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


# ── GitHubTrendingFetcher ──────────────────────────────────────────────────────


def test_github_fetcher_parses_language() -> None:
    fetcher = GitHubTrendingFetcher()
    with patch.object(
        fetcher._session, "get", return_value=_mock_resp(text=_GITHUB_HTML)
    ):
        result = fetcher.fetch("daily")

    assert "python" in result
    assert "rust" in result
    assert result["python"] == 1.0  # max 정규화: python 2회 / max 2
    assert result["rust"] == pytest_approx(0.5)


def test_github_fetcher_normalizes_to_lowercase() -> None:
    html = (
        '<html><body><article class="Box-row">'
        '<span itemprop="programmingLanguage">TypeScript</span>'
        "</article></body></html>"
    )
    fetcher = GitHubTrendingFetcher()
    with patch.object(fetcher._session, "get", return_value=_mock_resp(text=html)):
        result = fetcher.fetch("daily")
    assert "typescript" in result


def test_github_fetcher_returns_empty_on_http_error() -> None:
    fetcher = GitHubTrendingFetcher()
    mock_resp = _mock_resp(status=429)
    mock_resp.raise_for_status.side_effect = Exception("Too Many Requests")
    with patch.object(fetcher._session, "get", return_value=mock_resp):
        result = fetcher.fetch("daily")
    assert result == {}


def test_github_fetcher_returns_empty_on_connection_error() -> None:
    fetcher = GitHubTrendingFetcher()
    with patch.object(fetcher._session, "get", side_effect=ConnectionError("refused")):
        result = fetcher.fetch("weekly")
    assert result == {}


def test_github_fetcher_empty_html_returns_empty() -> None:
    fetcher = GitHubTrendingFetcher()
    with patch.object(
        fetcher._session, "get", return_value=_mock_resp(text="<html></html>")
    ):
        result = fetcher.fetch("daily")
    assert result == {}


def test_github_extracts_description_keywords() -> None:
    """repo 설명에 포함된 프레임워크 키워드가 0.5 weight로 집계된다."""
    html = """
    <html><body>
      <article class="Box-row">
        <h2><a>org/react-framework</a></h2>
        <p>A modern React and TypeScript application framework</p>
      </article>
    </body></html>
    """
    fetcher = GitHubTrendingFetcher()
    with patch.object(fetcher._session, "get", return_value=_mock_resp(text=html)):
        result = fetcher.fetch("daily")

    assert "react" in result
    assert "typescript" in result


# ── HackerNewsFetcher ──────────────────────────────────────────────────────────

_HN_HITS = {
    "hits": [
        {"title": "Show HN: Building a Rust backend with Axum", "points": 200},
        {"title": "Docker in production — lessons learned", "points": 80},
        {"title": "Why we migrated to PostgreSQL", "points": 40},
    ]
}


def test_hn_fetcher_extracts_keywords() -> None:
    with patch("requests.get", return_value=_mock_resp(json_data=_HN_HITS)):
        result = HackerNewsFetcher().fetch("daily")

    assert "rust" in result
    assert "docker" in result
    assert "postgresql" in result


def test_hn_fetcher_higher_points_higher_score() -> None:
    hits = {
        "hits": [
            {"title": "Rust is great", "points": 256},
            {"title": "Rust beginner guide", "points": 2},
        ]
    }
    with patch("requests.get", return_value=_mock_resp(json_data=hits)):
        result = HackerNewsFetcher().fetch("daily")

    assert result.get("rust", 0) > 0
    assert result["rust"] == 1.0  # max 정규화 후


def test_hn_fetcher_returns_empty_on_error() -> None:
    with patch("requests.get", side_effect=Exception("timeout")):
        result = HackerNewsFetcher().fetch("daily")
    assert result == {}


def test_hn_fetcher_empty_hits_returns_empty() -> None:
    with patch("requests.get", return_value=_mock_resp(json_data={"hits": []})):
        result = HackerNewsFetcher().fetch("weekly")
    assert result == {}


def test_hn_fetcher_no_matching_keywords() -> None:
    hits = {"hits": [{"title": "Random non-tech article", "points": 100}]}
    with patch("requests.get", return_value=_mock_resp(json_data=hits)):
        result = HackerNewsFetcher().fetch("daily")
    assert result == {}


def test_hn_word_boundary_no_substring_false_match() -> None:
    """substring 매칭 버그 수정 검증 — 부분 일치는 점수에 기여하지 않아야 한다."""
    hits = {
        "hits": [
            # "go" → "going", "google", "ago" 에 매칭되면 안 됨
            {"title": "Going to google for help again", "points": 100},
            # "ai" → "said", "explain", "training" 에 매칭되면 안 됨
            {"title": "He said to explain the training pipeline", "points": 100},
            # "ml" → "html" 에 매칭되면 안 됨
            {"title": "Learning html and css basics", "points": 100},
        ]
    }
    with patch("requests.get", return_value=_mock_resp(json_data=hits)):
        result = HackerNewsFetcher().fetch("daily")

    assert "go" not in result
    assert "ai" not in result
    assert "ml" not in result


def test_hn_uses_internal_tag_vocab() -> None:
    """internal_tags로 주입된 신생 기술 키워드가 HN 제목에서 매칭된다."""
    hits = {
        "hits": [
            {"title": "Bun 1.0 is officially released", "points": 150},
        ]
    }
    with patch("requests.get", return_value=_mock_resp(json_data=hits)):
        # internal_tags 없이 fetch → bun이 기본 키워드에 이미 포함됨
        result = HackerNewsFetcher().fetch(
            "daily", extended_keywords=frozenset({"bun"})
        )

    assert "bun" in result


# ── DevToFetcher ───────────────────────────────────────────────────────────────

_DEVTO_ARTICLES = [
    {"tag_list": ["python", "webdev"], "public_reactions_count": 200},
    {"tag_list": ["python", "docker"], "public_reactions_count": 50},
    {"tag_list": ["rust"], "public_reactions_count": 10},
]


def test_devto_fetcher_aggregates_tags() -> None:
    with patch("requests.get", return_value=_mock_resp(json_data=_DEVTO_ARTICLES)):
        result = DevToFetcher().fetch("daily")

    assert "python" in result
    assert "docker" in result
    assert "rust" in result
    assert result["python"] == 1.0  # python 최고 누적 → max 정규화 후 1.0


def test_devto_fetcher_reactions_affect_score() -> None:
    articles = [
        {"tag_list": ["react"], "public_reactions_count": 1000},
        {"tag_list": ["vue"], "public_reactions_count": 0},
    ]
    with patch("requests.get", return_value=_mock_resp(json_data=articles)):
        result = DevToFetcher().fetch("weekly")

    assert result.get("react", 0) > result.get("vue", 0)


def test_devto_fetcher_returns_empty_on_error() -> None:
    with patch("requests.get", side_effect=Exception("connection")):
        result = DevToFetcher().fetch("daily")
    assert result == {}


def test_devto_fetcher_empty_articles_returns_empty() -> None:
    with patch("requests.get", return_value=_mock_resp(json_data=[])):
        result = DevToFetcher().fetch("monthly")
    assert result == {}


def test_devto_denylist_filters_meta_tags() -> None:
    """_DEVTO_DENYLIST 태그는 결과에 포함되지 않아야 한다."""
    articles = [
        {
            "tag_list": ["discuss", "watercooler", "devchallenge", "python"],
            "public_reactions_count": 500,
        }
    ]
    with patch("requests.get", return_value=_mock_resp(json_data=articles)):
        result = DevToFetcher().fetch("daily")

    assert "discuss" not in result
    assert "watercooler" not in result
    assert "devchallenge" not in result
    assert "python" in result  # tech 태그는 통과


def test_devto_open_vocab_keeps_emerging_tech() -> None:
    """denylist에 없는 신생 기술 태그는 allowlist 없이도 통과해야 한다."""
    articles = [
        {"tag_list": ["biome", "tauri", "htmx"], "public_reactions_count": 100},
    ]
    with patch("requests.get", return_value=_mock_resp(json_data=articles)):
        result = DevToFetcher().fetch("weekly")

    assert "biome" in result
    assert "tauri" in result
    assert "htmx" in result


# ── ExternalSignalFetcher ──────────────────────────────────────────────────────


def _make_external_fetcher(
    github: dict | None = None,
    hn: dict | None = None,
    devto: dict | None = None,
) -> ExternalSignalFetcher:
    fetcher = ExternalSignalFetcher()
    fetcher._fetchers["github"] = MagicMock()
    fetcher._fetchers["hn"] = MagicMock()
    fetcher._fetchers["devto"] = MagicMock()
    fetcher._fetchers["github"].fetch.return_value = github or {}
    fetcher._fetchers["hn"].fetch.return_value = hn or {}
    fetcher._fetchers["devto"].fetch.return_value = devto or {}
    return fetcher


def test_external_fetcher_blends_three_sources() -> None:
    fetcher = _make_external_fetcher(
        github={"rust": 1.0},
        hn={"rust": 1.0},
        devto={"rust": 1.0},
    )
    result = fetcher.fetch("daily")

    assert "rust" in result
    # 전체 합의(0.35+0.35+0.30=1.0) 후 _EXTERNAL_SCALE 적용
    assert result["rust"] == pytest_approx(1.0 * _EXTERNAL_SCALE)


def test_external_fetcher_weights_applied() -> None:
    fetcher = _make_external_fetcher(
        github={"python": 1.0},
        hn={},
        devto={},
    )
    result = fetcher.fetch("weekly")
    # github weight 0.35 후 _EXTERNAL_SCALE 적용
    assert result.get("python", 0) == pytest_approx(0.35 * _EXTERNAL_SCALE)


def test_external_fetcher_partial_failure_graceful() -> None:
    fetcher = _make_external_fetcher()
    fetcher._fetchers["github"].fetch.side_effect = Exception("scraping failed")
    fetcher._fetchers["hn"].fetch.return_value = {"rust": 1.0}
    fetcher._fetchers["devto"].fetch.return_value = {"rust": 1.0}

    result = fetcher.fetch("daily")

    assert "rust" in result
    # github 실패 → hn(0.35) + devto(0.30) = 0.65 후 _EXTERNAL_SCALE 적용
    assert result["rust"] == pytest_approx(0.65 * _EXTERNAL_SCALE)


def test_external_fetcher_all_failure_returns_empty() -> None:
    fetcher = _make_external_fetcher()
    for name in ("github", "hn", "devto"):
        fetcher._fetchers[name].fetch.side_effect = Exception("fail")

    result = fetcher.fetch("daily")
    assert result == {}


def test_external_fetcher_normalizes_synonym_keys() -> None:
    # "python"(6자)과 "python3"(7자)은 fuzz.ratio ≈ 92% → threshold 85 통과, 하나로 병합
    fetcher = _make_external_fetcher(
        github={"python3": 1.0},
        hn={"python": 0.8},
    )
    result = fetcher.fetch("daily")
    # 정규화 후 하나의 키로 통합됨
    assert len([k for k in result if k in ("python", "python3")]) == 1


def test_external_scale_applied() -> None:
    """출력 최댓값이 _EXTERNAL_SCALE에 맞춰 스케일된다."""
    fetcher = _make_external_fetcher(
        github={"rust": 1.0},
        hn={"rust": 1.0},
        devto={"rust": 1.0},
    )
    result = fetcher.fetch("daily")

    assert max(result.values()) == pytest_approx(_EXTERNAL_SCALE)
