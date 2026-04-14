"""유사 콘텐츠 탐색 서비스 — FAISS devpick 인덱스 청크 집계 검색 (DP-288)."""

from __future__ import annotations

import logging

from app.rag.retriever import RAGRetriever
from app.schemas.similar_content import SimilarContent

logger = logging.getLogger(__name__)

_DEFAULT_INDEX_PATH = "data/vectors/devpick"
_MIN_SCORE_THRESHOLD = 0.3
_FETCH_MULTIPLIER = 10
_FETCH_CAP = 100


class SimilarContentService:
    """FAISS devpick 인덱스에서 유사 아티클을 검색한다.

    아티클은 청크 단위로 인덱싱되어 있으므로 FAISS 결과를 content_id 기준으로
    MAX 점수 집계한 뒤 아티클 레벨 추천 목록을 반환한다.
    LLM 호출 없음 — Bedrock 임베딩(쿼리 벡터화)만 발생한다.
    """

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        index_path: str = _DEFAULT_INDEX_PATH,
    ) -> None:
        self._retriever = RAGRetriever(
            aws_region=aws_region,
            index_path=index_path,
        )

    def search(
        self,
        text: str,
        top_k: int = 5,
        exclude_content_id: str | None = None,
    ) -> list[SimilarContent]:
        """유사 아티클을 검색하여 반환한다.

        청크 레벨 FAISS 결과를 content_id 기준으로 MAX 점수 집계한 뒤,
        threshold 필터와 자기 자신 제외를 적용하고 top_k개를 반환한다.

        Args:
            text: 검색 쿼리 텍스트 (제목 + 본문 합산 문자열).
            top_k: 반환할 최대 아티클 수.
            exclude_content_id: 제외할 아티클 ID (자기 자신 제외용).

        Returns:
            SimilarContent 리스트. 유사도 내림차순. 인덱스가 비어 있으면 빈 리스트.
        """
        # 청크 중복을 감안해 top_k * 10배 청크를 fetch, 최대 100개 상한
        fetch_k = min(top_k * _FETCH_MULTIPLIER, _FETCH_CAP)
        raw_results = self._retriever.search(text, top_k=fetch_k)

        # 청크 레벨 → content_id 레벨 MAX 점수 집계
        best_scores: dict[str, float] = {}
        for doc, score in raw_results:
            cid = doc.metadata.content_id
            if cid not in best_scores or score > best_scores[cid]:
                best_scores[cid] = score

        # 자기 자신 제외
        if exclude_content_id:
            best_scores.pop(exclude_content_id, None)

        # threshold 필터 → 점수 내림차순 정렬 → top_k 슬라이스
        results = [
            SimilarContent(content_id=cid, score=round(score, 4))
            for cid, score in sorted(
                best_scores.items(), key=lambda x: x[1], reverse=True
            )
            if score >= _MIN_SCORE_THRESHOLD
        ][:top_k]

        logger.info(
            "유사 콘텐츠 검색: query=%r, fetch_k=%d, unique_articles=%d, found=%d",
            text[:50],
            fetch_k,
            len(best_scores),
            len(results),
        )
        return results
