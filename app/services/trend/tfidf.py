"""TF-IDF 기반 키워드 추출 (DP-381)."""

from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer


class TfidfAnalyzer:
    """scikit-learn TfidfVectorizer 기반 상위 키워드 추출.

    tokenized_docs: KoreanTokenizer.tokenize() 결과 (공백 조인 문자열 리스트)
    반환: [(keyword, score), ...] 내림차순, len <= top_n
    """

    def __init__(
        self,
        top_n: int = 30,
        min_df: int = 2,
        max_df: float = 0.8,
        ngram_range: tuple[int, int] = (1, 2),
        max_features: int = 5000,
    ) -> None:
        self._top_n = top_n
        self._min_df = min_df
        self._max_df = max_df
        self._ngram_range = ngram_range
        self._max_features = max_features

    def extract(self, tokenized_docs: list[str]) -> list[tuple[str, float]]:
        """TF-IDF 피팅 후 상위 top_n 키워드를 반환한다.

        문서 수 < min_df 일 때 min_df=1 로 fallback (cold start 대응).
        """
        docs = [d for d in tokenized_docs if d]
        if not docs:
            return []

        cold_start = len(docs) < self._min_df
        effective_min_df = 1 if cold_start else self._min_df
        effective_max_df = 1.0 if cold_start else self._max_df
        vectorizer = TfidfVectorizer(
            min_df=effective_min_df,
            max_df=effective_max_df,
            ngram_range=self._ngram_range,
            max_features=self._max_features,
            token_pattern=r"(?u)\b\w+\b",
        )
        try:
            matrix = vectorizer.fit_transform(docs)
        except ValueError:
            return []

        terms = vectorizer.get_feature_names_out()
        scores = matrix.sum(axis=0).A1
        ranked = sorted(zip(terms, scores), key=lambda x: x[1], reverse=True)[
            : self._top_n
        ]
        return [(term, round(float(score), 4)) for term, score in ranked]
