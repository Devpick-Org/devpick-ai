"""TfidfAnalyzer 단위 테스트 (DP-381)."""

from __future__ import annotations

from app.services.trend.tfidf import TfidfAnalyzer


def _analyzer(**kwargs) -> TfidfAnalyzer:
    return TfidfAnalyzer(**kwargs)


def test_extract_returns_top_n() -> None:
    docs = [
        "react kubernetes docker",
        "react nextjs typescript",
        "kubernetes docker deploy",
        "typescript python golang",
        "python fastapi sqlalchemy",
    ]
    result = _analyzer(top_n=3).extract(docs)
    assert len(result) <= 3


def test_extract_sorted_desc() -> None:
    docs = [
        "react kubernetes docker",
        "react nextjs typescript",
        "kubernetes docker deploy",
        "typescript python golang",
        "python fastapi sqlalchemy",
    ]
    result = _analyzer().extract(docs)
    scores = [score for _, score in result]
    assert scores == sorted(scores, reverse=True)


def test_extract_empty_docs() -> None:
    assert _analyzer().extract([]) == []
    assert _analyzer().extract(["", "   ", ""]) == []


def test_extract_cold_start_fallback() -> None:
    # 문서 1개 → min_df=2 미달 → min_df=1 fallback으로 결과 반환
    docs = ["react kubernetes docker"]
    result = _analyzer(min_df=2).extract(docs)
    assert len(result) > 0


def test_extract_returns_tuple_format() -> None:
    docs = [
        "react kubernetes",
        "react docker",
        "kubernetes docker",
    ]
    result = _analyzer().extract(docs)
    assert len(result) > 0
    for item in result:
        assert isinstance(item, tuple)
        assert len(item) == 2
        assert isinstance(item[0], str)
        assert isinstance(item[1], float)
