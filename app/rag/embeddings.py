"""OpenAI 임베딩 서비스 래퍼 (DP-218)."""

from __future__ import annotations

import logging

from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """OpenAI text-embedding-3-small 기반 임베딩 생성.

    추후 self-hosted 모델로 교체 시 이 클래스만 수정하면 된다.
    """

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._model = OpenAIEmbeddings(
            api_key=api_key,
            model=model,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 리스트를 벡터 리스트로 변환한다.

        Args:
            texts: 임베딩할 텍스트 리스트

        Returns:
            각 텍스트에 대응하는 1536차원 벡터 리스트
        """
        if not texts:
            return []
        return self._model.embed_documents(texts)
