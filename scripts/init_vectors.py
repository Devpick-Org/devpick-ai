"""FAISS 벡터 인덱스 초기화 스크립트 (DP-218).

빈 FAISS 인덱스 파일을 생성한다.
서버 최초 배포 또는 인덱스 초기화 시 실행한다.

실행:
    python scripts/init_vectors.py
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
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        fail("OPENAI_API_KEY is required. Please set it in your environment or .env.")

    try:
        from langchain_openai import OpenAIEmbeddings

        from app.rag.vector_store import VectorStoreManager
    except ImportError as exc:
        fail(f"의존성 임포트 실패: {exc}")

    index_path = os.getenv("FAISS_INDEX_PATH", _INDEX_PATH)
    faiss_file = index_path + ".faiss"

    if os.path.exists(faiss_file):
        print(f"[init_vectors] 인덱스 이미 존재: {faiss_file} — 건너뜁니다.")
        return

    embedding_model = OpenAIEmbeddings(
        api_key=openai_api_key,
        model="text-embedding-3-small",
    )
    manager = VectorStoreManager(
        embedding_model=embedding_model,
        index_path=index_path,
    )
    manager.load_or_create()

    # 빈 인덱스는 문서 추가 전까지 파일이 없어도 정상 동작한다.
    # 최초 문서 삽입 시 자동 생성되므로 디렉터리만 보장한다.
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    print(f"[init_vectors] 벡터 디렉터리 준비 완료: {os.path.dirname(index_path)}")
    print(
        "[init_vectors] FAISS 인덱스는 첫 번째 embed_and_store 호출 시 자동 생성됩니다."
    )


if __name__ == "__main__":
    main()
