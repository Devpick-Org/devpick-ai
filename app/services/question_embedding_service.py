"""질문 임베딩 오케스트레이터 — 임베딩 → DynamoDB + FAISS 저장 (DP-234)."""

from __future__ import annotations

import logging

from app.rag.embeddings import EmbeddingService
from app.rag.store_manager import get_store
from app.rag.schemas import ChunkMetadata, RAGDocument
from app.repositories.question_vector_repository import QuestionVectorRepository

logger = logging.getLogger(__name__)

_DEFAULT_INDEX_PATH = "data/vectors/questions"


class QuestionEmbeddingOrchestrator:
    """질문 텍스트를 임베딩하여 DynamoDB와 FAISS에 저장한다.

    아티클 EmbeddingOrchestrator와 달리 청킹이 없다.
    질문은 짧으므로 전체 텍스트를 단일 문서로 임베딩한다.

    router.py에서 fire-and-forget 패턴으로 호출한다.
    실패 시 예외를 raise — 호출부에서 로그 후 무시.
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        index_path: str = _DEFAULT_INDEX_PATH,
    ) -> None:
        self._embedding_svc = EmbeddingService(aws_region=aws_region)
        self._vector_store = get_store(index_path, aws_region)
        self._question_repo = QuestionVectorRepository(aws_region=aws_region)

    def embed_and_store(
        self,
        question_id: str,
        text: str,
        suggested_tags: list[str] | None = None,
        content_id: str | None = None,
    ) -> None:
        """질문 텍스트를 임베딩하여 DynamoDB와 FAISS에 저장한다.

        Args:
            question_id: 질문 식별자.
            text: 임베딩 대상 텍스트 (refined_title + refined_content 결합).
            suggested_tags: 추천 태그 리스트 (optional).
            content_id: 관련 아티클 ID (optional).
        """
        if not text or not text.strip():
            logger.warning("질문 텍스트가 비어 있습니다 — question_id=%s", question_id)
            return

        embeddings = self._embedding_svc.embed([text])
        if not embeddings:
            logger.warning("임베딩 결과 없음 — question_id=%s", question_id)
            return

        embedding = embeddings[0]

        # DynamoDB 영구 저장
        self._question_repo.save_question(
            question_id=question_id,
            text=text,
            embedding=embedding,
            suggested_tags=suggested_tags,
            content_id=content_id,
        )

        # FAISS 인덱스 추가 (단일 문서)
        rag_doc = RAGDocument(
            text=text,
            metadata=ChunkMetadata(
                content_id=question_id,  # 질문 인덱스에서는 question_id를 content_id로 사용
                chunk_index=0,
                keywords=[],
                tags=suggested_tags or [],
            ),
        )
        self._vector_store.add_documents([rag_doc])
        self._vector_store.save()

        logger.info("질문 임베딩 완료: question_id=%s", question_id)
