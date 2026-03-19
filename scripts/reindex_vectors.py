"""MongoDB rag_documents에서 FAISS 인덱스를 재빌드하는 스크립트 (DP-218).

FAISS 파일이 유실되거나 손상된 경우 실행한다.
MongoDB에 저장된 벡터를 그대로 읽어 인덱스를 재구성하므로
원문 재수집/재임베딩이 필요 없다.

실행:
    python scripts/reindex_vectors.py

환경변수:
    MONGO_URI       (필수)
    OPENAI_API_KEY  (필수 — 임베딩 모델 초기화에 사용, API 호출 없음)
    MONGO_DB        (선택, 기본값: devpick)
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
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        fail("MONGO_URI is required. Please set it in your environment or .env.")

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        fail("OPENAI_API_KEY is required. Please set it in your environment or .env.")

    mongo_db = os.getenv("MONGO_DB", "devpick")
    index_path = os.getenv("FAISS_INDEX_PATH", _INDEX_PATH)

    try:
        from langchain_openai import OpenAIEmbeddings

        from app.rag.vector_store import VectorStoreManager
        from app.repositories.vector_repository import VectorRepository
    except ImportError as exc:
        fail(f"의존성 임포트 실패: {exc}")

    print(f"[reindex_vectors] MongoDB: {mongo_uri}, DB: {mongo_db}")
    print(f"[reindex_vectors] FAISS 인덱스 경로: {index_path}")

    vector_repo = VectorRepository(mongo_uri=mongo_uri, db_name=mongo_db)
    embedding_model = OpenAIEmbeddings(
        api_key=openai_api_key,
        model="text-embedding-3-small",
    )
    manager = VectorStoreManager(
        embedding_model=embedding_model,
        index_path=index_path,
    )
    # 기존 인덱스 무시하고 새로 빌드
    manager._store = None

    chunks = list(vector_repo.find_all())
    if not chunks:
        print(
            "[reindex_vectors] rag_documents 컬렉션이 비어 있습니다. 빌드할 데이터 없음."
        )
        return

    print(f"[reindex_vectors] {len(chunks)}개 청크 발견 — FAISS 재빌드 시작")

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

    # 저장된 벡터로 직접 인덱스 구성 (API 호출 없음)
    from langchain_community.vectorstores import FAISS

    store = FAISS.from_embeddings(
        text_embeddings=list(zip(texts, [chunk["embedding"] for chunk in chunks])),
        embedding=embedding_model,
        metadatas=metadatas,
    )
    manager._store = store
    manager.save()

    print(f"[reindex_vectors] FAISS 재빌드 완료: {len(chunks)}개 청크 → {index_path}")


if __name__ == "__main__":
    main()
