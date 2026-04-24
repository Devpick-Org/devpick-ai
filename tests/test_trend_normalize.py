"""TagNormalizer 단위 테스트 (DP-380)."""

from __future__ import annotations

from app.services.trend.normalize import TagNormalizer


def test_normalize_empty_list() -> None:
    normalizer = TagNormalizer()
    assert normalizer.normalize([]) == []


def test_normalize_identical_tags() -> None:
    normalizer = TagNormalizer()
    result = normalizer.normalize(["react", "react"])
    assert result == ["react", "react"]


def test_normalize_case_insensitive() -> None:
    normalizer = TagNormalizer()
    result = normalizer.normalize(["Python", "PYTHON", "python"])
    assert result == ["python", "python", "python"]


def test_normalize_unrelated_tags() -> None:
    normalizer = TagNormalizer()
    result = normalizer.normalize(["python", "javascript"])
    assert result == ["python", "javascript"]


def test_normalize_synonym_groups() -> None:
    normalizer = TagNormalizer(threshold=85)
    # python3 (ratio ~92 with python) → python으로 통합
    result = normalizer.normalize(["python", "python3"])
    assert result[0] == "python"
    assert result[1] == "python"
