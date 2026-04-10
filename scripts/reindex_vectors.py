"""DynamoDB rag_documents에서 FAISS 인덱스를 재빌드하는 스크립트 (DP-218).

FAISS 파일이 유실되거나 손상된 경우 실행한다.
DynamoDB에 저장된 벡터를 그대로 읽어 인덱스를 재구성하므로
원문 재수집/재임베딩이 필요 없다.

⚠️ 차원 주의: 임베딩 모델이 OpenAI(1536차원) → Bedrock Titan v2(1024차원)로
전환되었습니다. DynamoDB에 저장된 벡터가 1024차원이어야 합니다.
기존 OpenAI 기반 벡터가 남아 있다면 재수집/재임베딩이 필요합니다.

실행:
    python scripts/reindex_vectors.py

환경변수:
    AWS_REGION       (선택, 기본값: ap-northeast-2)
    FAISS_INDEX_PATH (선택, 기본값: data/vectors/devpick)
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

_INDEX_PATH = "data/vectors/devpick"


def fail(message: str) -> None:
    print(f"[reindex_vectors] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    aws_region = os.getenv("AWS_REGION", "ap-northeast-2")
    index_path = os.getenv("FAISS_INDEX_PATH", _INDEX_PATH)

    print(f"[reindex_vectors] AWS 리전: {aws_region}")
    print(f"[reindex_vectors] FAISS 인덱스 경로: {index_path}")

    try:
        from langchain_community.vectorstores import FAISS

        from app.rag.embeddings import BedrockEmbeddingsAdapter, EmbeddingService
        from app.rag.vector_store import VectorStoreManager
        from app.repositories.vector_repository import VectorRepository
    except ImportError as exc:
        fail(f"의존성 임포트 실패: {exc}")

    vector_repo = VectorRepository(aws_region=aws_region)
    chunks = list(vector_repo.find_all())

    if not chunks:
        print(
            "[reindex_vectors] DynamoDB rag_documents 테이블이 비어 있습니다. 빌드할 데이터 없음."
        )
        return

    print(f"[reindex_vectors] {len(chunks)}개 청크 발견 — FAISS 재빌드 시작")

    embedding_model = BedrockEmbeddingsAdapter(
        service=EmbeddingService(aws_region=aws_region)
    )
    manager = VectorStoreManager(
        embedding_model=embedding_model,
        index_path=index_path,
    )
    manager._store = None  # 기존 인덱스 무시하고 새로 빌드

    texts = [chunk["text"] for chunk in chunks]
    metadatas = [
        {
            "content_id": chunk["content_id"],
            "chunk_index": chunk["chunk_index"],
            "keywords": chunk.get("keywords", []),
            "tags": chunk.get("tags", []),
        }
        for chunk in chunks
    ]
    embeddings = [chunk["embedding"] for chunk in chunks]

    # 저장된 벡터로 직접 인덱스 구성 (API 호출 없음)
    store = FAISS.from_embeddings(
        text_embeddings=list(zip(texts, embeddings)),
        embedding=embedding_model,
        metadatas=metadatas,
    )
    manager._store = store
    manager.save()

    print(f"[reindex_vectors] FAISS 재빌드 완료: {len(chunks)}개 청크 → {index_path}")
    print("[reindex_vectors] 임베딩 모델: Bedrock Titan Embeddings v2 (1024차원)")


if __name__ == "__main__":
    main()
