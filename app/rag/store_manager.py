"""FAISS VectorStoreManager 싱글턴 관리 (#18).

매 요청마다 FAISS 파일을 로드하는 성능 문제를 해소한다.
index_path를 키로 VectorStoreManager를 모듈 레벨에 캐시한다.
"""

from __future__ import annotations

import threading

from app.rag.embeddings import BedrockEmbeddingsAdapter, EmbeddingService
from app.rag.vector_store import VectorStoreManager

_stores: dict[str, VectorStoreManager] = {}
_init_lock = threading.Lock()


def get_store(
    index_path: str,
    aws_region: str = "ap-northeast-2",
) -> VectorStoreManager:
    """index_path 기준 VectorStoreManager 싱글턴을 반환한다.

    최초 호출 시 EmbeddingService + VectorStoreManager를 초기화하고
    load_or_create()를 실행한 뒤 모듈 변수에 캐시한다.
    이후 호출은 캐시된 인스턴스를 즉시 반환한다.

    Args:
        index_path: FAISS 인덱스 파일 경로 (확장자 제외).
        aws_region: AWS 리전 (EmbeddingService용).
    """
    if index_path in _stores:
        return _stores[index_path]

    with _init_lock:
        # double-checked locking
        if index_path not in _stores:
            embedding_svc = EmbeddingService(aws_region=aws_region)
            adapter = BedrockEmbeddingsAdapter(service=embedding_svc)
            store = VectorStoreManager(embedding_model=adapter, index_path=index_path)
            store.load_or_create()
            _stores[index_path] = store

    return _stores[index_path]
