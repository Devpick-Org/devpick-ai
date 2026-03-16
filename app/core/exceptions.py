"""AI 서버 커스텀 예외 계층 (DP-223).

백엔드(Spring Boot)가 HTTP 상태코드로 AI_001/002/003을 구분한다.
에러는 HTTP 상태코드로만 표현한다 — 별도 에러 코드 필드 없음.
"""

from __future__ import annotations


class AIServiceError(Exception):
    """AI 서비스 에러 베이스 클래스."""

    status_code: int = 500
    message: str = "AI 서비스 에러"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.__class__.message
        super().__init__(self.message)


class AIBadRequestError(AIServiceError):
    """잘못된 입력 (level, text) — 400."""

    status_code = 400
    message = "잘못된 요청입니다"


class AIUpstreamError(AIServiceError):
    """LLM 연결 실패 / API 에러 / Rate Limit — 502."""

    status_code = 502
    message = "AI 업스트림 오류입니다"


class AITimeoutError(AIServiceError):
    """LLM 타임아웃 — 504."""

    status_code = 504
    message = "AI 응답 시간이 초과됐습니다"


class AIInternalError(AIServiceError):
    """인증 실패 / 파싱 실패 / tool_use 없음 — 500."""

    status_code = 500
    message = "AI 내부 오류입니다"
