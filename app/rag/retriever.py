"""RAG 검색 인터페이스 (DP-218).

후속 티켓(DP-233 AI 답변 생성, DP-231 질문 개선)에서 사용한다.
"""

from __future__ import annotations

import logging

from langchain_openai import OpenAIEmbeddings

from app.rag.schemas import RAGDocument
from app.rag.vector_store import VectorStoreManager

logger = logging.getLogger(__name__)

_DEFAULT_INDEX_PATH = "data/vectors/devpick"


class RAGRetriever:
    """FAISS 인덱스에서 쿼리와 유사한 청크를 검색한다.

    DP-233(AI 답변), DP-231(질문 개선) 등에서 다음과 같이 사용한다::

        retriever = RAGRetriever(openai_api_key=OPENAI_API_KEY)
        results = retriever.search("Redis TTL이란?", top_k=5)
        context = "\\n\\n".join(doc.text for doc, _ in results)
    """

    def __init__(
        self,
        openai_api_key: str,
        index_path: str = _DEFAULT_INDEX_PATH,
        model: str = "text-embedding-3-small",
    ) -> None:
        embedding_model = OpenAIEmbeddings(api_key=openai_api_key, model=model)
        self._store = VectorStoreManager(
            embedding_model=embedding_model,
            index_path=index_path,
        )
        self._store.load_or_create()

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[tuple[RAGDocument, float]]:
        """쿼리와 유사한 청크를 검색한다.

        Args:
            query: 검색 쿼리 (자연어 질문 또는 키워드)
            top_k: 반환할 최대 청크 수

        Returns:
            (RAGDocument, similarity_score) 튜플 리스트.
            유사도 높은 순으로 정렬. 인덱스가 비어 있으면 빈 리스트 반환.
        """
        results = self._store.search(query, top_k=top_k)
        logger.info(
            "RAG 검색: query=%r, top_k=%d, found=%d", query, top_k, len(results)
        )
        return results
