"""Bedrock Titan Embeddings v2 서비스 래퍼."""

from __future__ import annotations

import json
import logging

import boto3
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)

_MODEL_ID = "amazon.titan-embed-text-v2:0"
_DIMENSIONS = 1024


class EmbeddingService:
    """Amazon Bedrock Titan Embeddings v2 기반 임베딩 생성 (1024차원).

    OpenAI text-embedding-3-small (1536차원) 에서 전환.
    EC2 IAM Role로 인증 — API 키 불필요.
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        model_id: str = _MODEL_ID,
    ) -> None:
        self._client = boto3.client("bedrock-runtime", region_name=aws_region)
        self._model_id = model_id

    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 리스트를 벡터 리스트로 변환한다.

        Args:
            texts: 임베딩할 텍스트 리스트

        Returns:
            각 텍스트에 대응하는 1024차원 벡터 리스트
        """
        if not texts:
            return []

        embeddings: list[list[float]] = []
        for text in texts:
            response = self._client.invoke_model(
                modelId=self._model_id,
                body=json.dumps(
                    {"inputText": text, "dimensions": _DIMENSIONS, "normalize": True}
                ),
                contentType="application/json",
                accept="application/json",
            )
            body = json.loads(response["body"].read())
            embeddings.append(body["embedding"])

        return embeddings


class BedrockEmbeddingsAdapter(Embeddings):
    """LangChain Embeddings 인터페이스를 구현하는 Bedrock 어댑터.

    VectorStoreManager(FAISS)에서 사용한다.
    """

    def __init__(self, service: EmbeddingService) -> None:
        self._service = service

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._service.embed(texts)

    def embed_query(self, text: str) -> list[float]:
        result = self._service.embed([text])
        return result[0] if result else []
