"""질문(post) 삭제 시 ai_answers, rag_questions, FAISS 질문 인덱스 정리."""

from __future__ import annotations

import logging

from app.rag.store_manager import get_store
from app.repositories.answer_repository import AnswerRepository
from app.repositories.question_vector_repository import QuestionVectorRepository

logger = logging.getLogger(__name__)

_DEFAULT_QUESTIONS_INDEX = "data/vectors/questions"


def cleanup_question_documents(question_id: str, aws_region: str) -> None:
    """백엔드 posts 삭제 후 호출 — DynamoDB 두 테이블과 FAISS questions 인덱스에서 해당 질문 제거.

    각 단계 실패는 로그만 남기고 다음 단계를 시도한다(부분 정리라도 수행).
    """
    try:
        AnswerRepository(aws_region=aws_region).delete_by_question_id(question_id)
    except Exception:
        logger.exception("Failed to delete ai_answers for question_id=%s", question_id)

    try:
        QuestionVectorRepository(aws_region=aws_region).delete_by_question_id(
            question_id
        )
    except Exception:
        logger.exception("Failed to delete rag_questions for question_id=%s", question_id)

    try:
        store = get_store(_DEFAULT_QUESTIONS_INDEX, aws_region)
        store.delete_by_content_id(question_id)
        store.save()
    except Exception:
        logger.exception("Failed to remove question from FAISS: question_id=%s", question_id)
