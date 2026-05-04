"""YouTubeCollector._map_tags() 단위 테스트."""

from __future__ import annotations

from app.collectors.backfill.youtube import YouTubeCollector


def _video(
    title: str = "",
    description: str = "",
    snippet_tags: list[str] | None = None,
) -> dict:
    snippet: dict = {"title": title, "description": description}
    if snippet_tags is not None:
        snippet["tags"] = snippet_tags
    return {"snippet": snippet}


# ── 기존 동작 (title + description 매칭) ─────────────────────────────────────


def test_map_tags_matches_tag_in_title() -> None:
    video = _video(title="Python 튜토리얼")
    result = YouTubeCollector._map_tags(video, ["Python", "React"])
    assert "Python" in result
    assert "React" not in result


def test_map_tags_matches_tag_in_description() -> None:
    video = _video(description="This video covers Docker and Kubernetes basics.")
    result = YouTubeCollector._map_tags(video, ["Docker", "React"])
    assert "Docker" in result
    assert "React" not in result


def test_map_tags_case_insensitive_text_blob() -> None:
    video = _video(title="REACT for beginners")
    result = YouTubeCollector._map_tags(video, ["React"])
    assert "React" in result


# ── snippet.tags 매칭 (신규) ──────────────────────────────────────────────────


def test_map_tags_matches_from_snippet_tags() -> None:
    video = _video(title="빌드 최적화 전략", snippet_tags=["Docker", "CI/CD"])
    result = YouTubeCollector._map_tags(video, ["Docker", "React"])
    assert "Docker" in result
    assert "React" not in result


def test_map_tags_snippet_tags_case_insensitive() -> None:
    video = _video(snippet_tags=["PYTHON"])
    result = YouTubeCollector._map_tags(video, ["Python"])
    assert "Python" in result


def test_map_tags_snippet_tags_none_does_not_crash() -> None:
    video = _video(title="Python tutorial")
    result = YouTubeCollector._map_tags(video, ["Python"])
    assert "Python" in result


def test_map_tags_snippet_tags_empty_does_not_crash() -> None:
    video = _video(title="Python tutorial", snippet_tags=[])
    result = YouTubeCollector._map_tags(video, ["Python"])
    assert "Python" in result


def test_map_tags_no_match_returns_empty() -> None:
    video = _video(title="재미있는 요리 영상", snippet_tags=["cooking"])
    result = YouTubeCollector._map_tags(video, ["Python", "React"])
    assert result == []
