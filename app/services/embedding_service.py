"""임베딩 오케스트레이터 — 청킹 → 임베딩 → 저장 흐름 조율 (DP-218)."""

from __future__ import annotations

import logging

from app.rag.chunker import DocumentChunker
from app.rag.embeddings import BedrockEmbeddingsAdapter, EmbeddingService
from app.rag.vector_store import VectorStoreManager
from app.repositories.vector_repository import VectorRepository
from app.schemas.summary import AllLevelsSummaryResponse

logger = logging.getLogger(__name__)

_DEFAULT_INDEX_PATH = "data/vectors/devpick"


class EmbeddingOrchestrator:
    """요약 완료 후 원문 청킹 → 임베딩 → MongoDB + FAISS 저장을 순서대로 수행한다.

    router.py에서 fire-and-forget 패턴으로 호출한다.
    실패 시 예외를 raise — 호출부에서 로그 후 무시.
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        index_path: str = _DEFAULT_INDEX_PATH,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        embedding_svc = EmbeddingService(aws_region=aws_region)
        self._embedding_svc = embedding_svc
        self._chunker = DocumentChunker(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        self._vector_store = VectorStoreManager(
            embedding_model=BedrockEmbeddingsAdapter(service=embedding_svc),
            index_path=index_path,
        )
        self._vector_repo = VectorRepository(aws_region=aws_region)
        self._vector_store.load_or_create()

    def embed_and_store(
        self,
        content_id: str,
        preprocessed_text: str,
        summary: AllLevelsSummaryResponse,
    ) -> None:
        """원문을 청킹하고 임베딩하여 MongoDB와 FAISS에 저장한다.

        Args:
            content_id: 콘텐츠 식별자
            preprocessed_text: PreprocessService 출력 텍스트
            summary: 메타데이터(keywords, tags) 추출용 요약 응답 객체
        """
        keywords = summary.common.keywords
        tags = summary.common.tags

        docs = self._chunker.chunk(
            content_id=content_id,
            text=preprocessed_text,
            keywords=keywords,
            tags=tags,
        )

        if not docs:
            logger.warning("청킹 결과 없음 — content_id=%s", content_id)
            return

        texts = [doc.text for doc in docs]
        embeddings = self._embedding_svc.embed(texts)

        # MongoDB 영구 저장
        mongo_chunks = [
            {
                "content_id": doc.metadata.content_id,
                "chunk_index": doc.metadata.chunk_index,
                "text": doc.text,
                "embedding": embedding,
                "keywords": doc.metadata.keywords,
                "tags": doc.metadata.tags,
            }
            for doc, embedding in zip(docs, embeddings)
        ]
        self._vector_repo.save_chunks(mongo_chunks)

        # FAISS 인덱스 추가 + 저장
        self._vector_store.add_documents(docs)
        self._vector_store.save()

        logger.info(
            "임베딩 완료: content_id=%s, chunks=%d",
            content_id,
            len(docs),
        )
