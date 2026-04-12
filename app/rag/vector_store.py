"""FAISS 벡터 인덱스 관리 (DP-218)."""

from __future__ import annotations

import logging
import os
import threading

from typing import Any

from langchain_community.vectorstores import FAISS

from app.rag.schemas import ChunkMetadata, RAGDocument

logger = logging.getLogger(__name__)

_INDEX_SUFFIX = ".faiss"


def _normalize_faiss_score(raw: float) -> float:
    """FAISS 내적 유사도를 [0, 1] 구간으로 맞춘다 (유사 질문 threshold 등과 호환)."""
    if 0.0 <= raw <= 1.0:
        return raw
    # L2 정규화 벡터의 내적은 대개 [-1, 1] 근처
    return max(0.0, min(1.0, (raw + 1.0) / 2.0))


_PKL_SUFFIX = ".pkl"


class VectorStoreManager:
    """FAISS 인덱스 생성, 추가, 검색, 저장/로드를 담당한다.

    동시 쓰기 안전: threading.Lock으로 add/save 보호.
    """

    def __init__(
        self,
        embedding_model: Any,  # langchain_core.embeddings.Embeddings 호환
        index_path: str = "data/vectors/devpick",
    ) -> None:
        self._embedding_model = embedding_model
        self._index_path = index_path
        self._store: FAISS | None = None
        self._lock = threading.Lock()

    def load_or_create(self) -> None:
        """FAISS 인덱스 파일이 있으면 로드, 없으면 빈 상태로 초기화한다."""
        faiss_file = self._index_path + _INDEX_SUFFIX
        if os.path.exists(faiss_file):
            folder, name = os.path.split(self._index_path)
            self._store = FAISS.load_local(
                folder_path=folder,
                embeddings=self._embedding_model,
                index_name=name,
                allow_dangerous_deserialization=True,
            )
            logger.info("FAISS 인덱스 로드 완료: %s", self._index_path)
        else:
            self._store = None
            logger.info("FAISS 인덱스 없음 — 첫 문서 추가 시 생성됩니다")

    def add_documents(self, docs: list[RAGDocument]) -> None:
        """RAGDocument 리스트를 FAISS 인덱스에 추가한다."""
        if not docs:
            return

        texts = [doc.text for doc in docs]
        metadatas = [doc.metadata.model_dump() for doc in docs]

        with self._lock:
            if self._store is None:
                self._store = FAISS.from_texts(
                    texts=texts,
                    embedding=self._embedding_model,
                    metadatas=metadatas,
                )
            else:
                self._store.add_texts(texts=texts, metadatas=metadatas)

        logger.info("FAISS에 %d개 청크 추가됨", len(docs))

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[tuple[RAGDocument, float]]:
        """쿼리와 유사한 청크를 검색한다.

        Returns:
            (RAGDocument, similarity_score) 튜플 리스트. 점수 높을수록 유사.
        """
        if self._store is None:
            logger.warning("FAISS 인덱스가 비어 있습니다")
            return []

        # similarity_search_with_relevance_scores 는 [0,1] 점수를 기대하지만,
        # IndexFlatIP(내적) 인덱스는 음수·1 초과 값이 나와 UserWarning이 난다.
        results = self._store.similarity_search_with_score(query, k=top_k)
        output = []
        for lc_doc, raw in results:
            score = _normalize_faiss_score(float(raw))
            metadata = ChunkMetadata(**lc_doc.metadata)
            rag_doc = RAGDocument(text=lc_doc.page_content, metadata=metadata)
            output.append((rag_doc, score))
        return output

    def save(self) -> None:
        """FAISS 인덱스를 파일로 저장한다."""
        if self._store is None:
            return

        folder, name = os.path.split(self._index_path)
        os.makedirs(folder, exist_ok=True)

        with self._lock:
            self._store.save_local(folder_path=folder, index_name=name)

        logger.info("FAISS 인덱스 저장 완료: %s", self._index_path)

    def delete_by_content_id(self, content_id: str) -> None:
        """특정 content_id의 모든 청크를 인덱스에서 제거한다.

        Note: LangChain FAISS wrapper는 개별 삭제를 지원하지 않으므로
        해당 content_id를 제외하고 재빌드한다.
        """
        if self._store is None:
            return

        all_docs = self._store.docstore._dict
        remaining_texts = []
        remaining_metadatas = []

        for doc_id, doc in all_docs.items():
            if doc.metadata.get("content_id") != content_id:
                remaining_texts.append(doc.page_content)
                remaining_metadatas.append(doc.metadata)

        with self._lock:
            if remaining_texts:
                self._store = FAISS.from_texts(
                    texts=remaining_texts,
                    embedding=self._embedding_model,
                    metadatas=remaining_metadatas,
                )
            else:
                self._store = None

        logger.info("content_id=%s 청크 삭제 완료", content_id)
