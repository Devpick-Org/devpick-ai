"""유사 질문 탐색 서비스 — FAISS questions 인덱스 검색 (DP-235)."""

from __future__ import annotations

import logging

from app.rag.retriever import RAGRetriever
from app.schemas.similar_question import SimilarQuestion

logger = logging.getLogger(__name__)

_DEFAULT_INDEX_PATH = "data/vectors/questions"
_MIN_SCORE_THRESHOLD = 0.3


class SimilarQuestionService:
    """FAISS questions 인덱스에서 유사 질문을 검색한다.

    QuestionEmbeddingOrchestrator(DP-234)가 저장한 인덱스를 읽기 전용으로 활용한다.
    LLM 호출 없음 — OpenAI 임베딩(쿼리 벡터화)만 발생한다.
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
        exclude_question_id: str | None = None,
    ) -> list[SimilarQuestion]:
        """유사 질문을 검색하여 반환한다.

        Args:
            text: 검색 쿼리 텍스트.
            top_k: 반환할 최대 결과 수.
            exclude_question_id: 제외할 질문 ID (자기 자신 제외용).

        Returns:
            SimilarQuestion 리스트. 유사도 내림차순. 빈 인덱스이면 빈 리스트.
        """
        # exclude 시 필터링 후에도 top_k개 확보하기 위해 넉넉히 가져옴
        fetch_k = top_k + 5 if exclude_question_id else top_k
        raw_results = self._retriever.search(text, top_k=fetch_k)

        results: list[SimilarQuestion] = []
        for doc, score in raw_results:
            if exclude_question_id and doc.metadata.content_id == exclude_question_id:
                continue
            if score < _MIN_SCORE_THRESHOLD:
                continue
            results.append(
                SimilarQuestion(
                    question_id=doc.metadata.content_id,
                    score=round(score, 4),
                    tags=doc.metadata.tags,
                )
            )
            if len(results) >= top_k:
                break

        logger.info(
            "유사 질문 검색: query=%r, top_k=%d, found=%d",
            text[:50],
            top_k,
            len(results),
        )
        return results
