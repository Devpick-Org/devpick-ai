"""KoreanTokenizer 단위 테스트 (DP-381)."""

from __future__ import annotations

from app.services.trend.tokenizer import KoreanTokenizer


def _tokenizer() -> KoreanTokenizer:
    return KoreanTokenizer()


def test_tokenize_one_extracts_nouns() -> None:
    result = _tokenizer().tokenize_one("파이썬으로 머신러닝 모델을 구현했다")
    assert "파이썬" in result
    assert "머신러닝" in result or "모델" in result
    # 조사/어미는 제외
    for token in result:
        assert token not in {"으로", "을", "다"}


def test_tokenize_one_filters_short_tokens() -> None:
    result = _tokenizer().tokenize_one("나는 AI를 공부한다")
    for token in result:
        assert len(token) >= 2


def test_tokenize_one_filters_numbers_only() -> None:
    result = _tokenizer().tokenize_one("2024년 1월에 123개의 서비스를 배포했다")
    for token in result:
        assert not token.isdigit()


def test_tokenize_one_empty_input() -> None:
    tok = _tokenizer()
    assert tok.tokenize_one("") == []
    assert tok.tokenize_one("   ") == []


def test_tokenize_joins_with_space() -> None:
    texts = ["파이썬 서버", "쿠버네티스 배포"]
    result = _tokenizer().tokenize(texts)
    assert len(result) == 2
    for doc in result:
        assert isinstance(doc, str)
        # 복수 토큰이면 공백으로 연결
        tokens = doc.split()
        for t in tokens:
            assert len(t) >= 2
