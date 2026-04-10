"""FAISS 벡터 인덱스 초기화 스크립트 (DP-218).

빈 FAISS 인덱스를 위한 벡터 디렉터리를 준비한다.
서버 최초 배포 또는 인덱스 초기화 시 실행한다.

인덱스 파일은 첫 번째 embed_and_store 호출 시 자동 생성되므로
이 스크립트는 디렉터리 생성만 보장한다.

실행:
    python scripts/init_vectors.py

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
    print(f"[init_vectors] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    aws_region = os.getenv("AWS_REGION", "ap-northeast-2")
    index_path = os.getenv("FAISS_INDEX_PATH", _INDEX_PATH)
    faiss_file = index_path + ".faiss"

    if os.path.exists(faiss_file):
        print(f"[init_vectors] 인덱스 이미 존재: {faiss_file} — 건너뜁니다.")
        return

    try:
        from app.rag.embeddings import BedrockEmbeddingsAdapter, EmbeddingService
        from app.rag.vector_store import VectorStoreManager
    except ImportError as exc:
        fail(f"의존성 임포트 실패: {exc}")

    embedding_model = BedrockEmbeddingsAdapter(
        service=EmbeddingService(aws_region=aws_region)
    )
    manager = VectorStoreManager(
        embedding_model=embedding_model,
        index_path=index_path,
    )
    manager.load_or_create()

    os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
    print(f"[init_vectors] 벡터 디렉터리 준비 완료: {os.path.dirname(index_path)}")
    print(
        "[init_vectors] FAISS 인덱스는 첫 번째 embed_and_store 호출 시 자동 생성됩니다."
    )
    print(
        f"[init_vectors] 임베딩 모델: Bedrock Titan Embeddings v2 (1024차원), region={aws_region}"
    )


if __name__ == "__main__":
    main()
