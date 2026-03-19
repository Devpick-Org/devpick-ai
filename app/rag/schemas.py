"""RAG 파이프라인 Pydantic 스키마 (DP-218)."""

from __future__ import annotations

from pydantic import BaseModel


class ChunkMetadata(BaseModel):
    """벡터 문서 메타데이터 — 검색 필터링 및 결과 추적용."""

    content_id: str
    chunk_index: int
    keywords: list[str] = []
    tags: list[str] = []


class RAGDocument(BaseModel):
    """임베딩 대상 청크 문서."""

    text: str
    metadata: ChunkMetadata
