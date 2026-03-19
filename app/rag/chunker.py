"""문서 청킹 — 전처리된 원문을 임베딩 단위로 분할한다 (DP-218)."""

from __future__ import annotations

import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.schemas import ChunkMetadata, RAGDocument

logger = logging.getLogger(__name__)


class DocumentChunker:
    """전처리된 원문 텍스트를 body chunk 단위로 분할한다.

    MVP는 body chunk 하나만 사용한다.
    향후 section / document chunk 추가 시 이 클래스를 확장한다.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk(
        self,
        content_id: str,
        text: str,
        keywords: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[RAGDocument]:
        """원문 텍스트를 body chunk 리스트로 변환한다.

        Args:
            content_id: 콘텐츠 식별자
            text: 전처리된 원문 텍스트 (PreprocessService 출력)
            keywords: 필터링용 키워드 목록
            tags: 필터링용 태그 목록

        Returns:
            RAGDocument 리스트. 빈 텍스트면 빈 리스트 반환.
        """
        if not text or not text.strip():
            logger.warning(
                "chunk() called with empty text for content_id=%s", content_id
            )
            return []

        chunks = self._splitter.split_text(text)
        return [
            RAGDocument(
                text=chunk,
                metadata=ChunkMetadata(
                    content_id=content_id,
                    chunk_index=i,
                    keywords=keywords or [],
                    tags=tags or [],
                ),
            )
            for i, chunk in enumerate(chunks)
        ]
