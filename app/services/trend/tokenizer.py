"""한국어 형태소 기반 토크나이저 (DP-381)."""

from __future__ import annotations

from pathlib import Path

from kiwipiepy import Kiwi

_ALLOWED_POS = {"NNG", "NNP", "SL"}
_MIN_LENGTH = 2
_DEFAULT_STOPWORDS_PATH = (
    Path(__file__).resolve().parents[2] / "core" / "data" / "stopwords_ko.txt"
)


def _load_stopwords(path: Path) -> set[str]:
    words: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        words.add(line.lower())
    return words


class KoreanTokenizer:
    """kiwipiepy 기반 한국어 토크나이저.

    POS 필터: NNG(일반명사) / NNP(고유명사) / SL(외래어)
    min_length=2, 순수 숫자 토큰 제외, 불용어 제거
    """

    def __init__(self, stopwords_path: Path | None = None) -> None:
        self._kiwi = Kiwi()
        self._stopwords = _load_stopwords(stopwords_path or _DEFAULT_STOPWORDS_PATH)

    def tokenize_one(self, text: str) -> list[str]:
        """단일 텍스트를 필터링된 토큰 리스트로 변환."""
        if not text or not text.strip():
            return []
        tokens: list[str] = []
        for token in self._kiwi.tokenize(text):
            if token.tag not in _ALLOWED_POS:
                continue
            form = token.form.lower().strip()
            if len(form) < _MIN_LENGTH:
                continue
            if form.isdigit():
                continue
            if form in self._stopwords:
                continue
            tokens.append(form)
        return tokens

    def tokenize(self, texts: list[str]) -> list[str]:
        """복수 텍스트를 TfidfVectorizer 입력용 공백 조인 문자열 리스트로 변환."""
        return [" ".join(self.tokenize_one(t)) for t in texts]
