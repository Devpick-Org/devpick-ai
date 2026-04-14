"""유사 콘텐츠 탐색 입출력 스키마 (DP-288)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SimilarContentRequest(BaseModel):
    """유사 콘텐츠 검색 요청 스키마 — 백엔드 SimilarContentRequest 대응."""

    text: str = Field(min_length=1)
    # 제목 + 본문을 합친 문자열. 쿼리 임베딩의 입력이 된다.

    content_id: str | None = None
    # 자기 자신 제외용 아티클 ID. 없으면 self-exclusion 없음.

    top_k: int = Field(default=5, ge=1, le=20)
    # 반환할 최대 유사 아티클 수.

    user_id: str | None = None
    # 이벤트 로그용 — 없으면 이벤트 로깅 스킵.


class SimilarContent(BaseModel):
    """유사 콘텐츠 개별 항목."""

    content_id: str
    # 유사 아티클의 ID (청크 집계 기반).

    score: float = Field(ge=0.0, le=1.0)
    # 아티클 레벨 집계 유사도 점수 (청크 MAX 기반, 소수점 4자리 반올림).


class SimilarContentResponse(BaseModel):
    """유사 콘텐츠 검색 결과 응답 스키마."""

    results: list[SimilarContent]
    # 유사 아티클 리스트, 유사도 내림차순.

    total: int
    # 반환된 결과 수.
