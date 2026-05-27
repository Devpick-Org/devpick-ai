"""질문 임베딩 인덱싱 입력 스키마."""

from __future__ import annotations

from pydantic import BaseModel, Field


class QuestionIndexRequest(BaseModel):
    """POST /internal/questions 요청 스키마.

    Spring 백엔드가 TECH 게시글 생성 직후 호출한다.
    질문을 FAISS questions 인덱스에 임베딩/인덱싱만 수행하고 답변은 생성하지 않는다.
    """

    question_id: str
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    user_id: str
