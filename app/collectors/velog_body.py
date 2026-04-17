"""Velog GraphQL 본문(markdown) 정규화 — DB 저장·프론트 렌더 오류 방지 (DP-313)."""


def sanitize_velog_body(body: str | None) -> str | None:
    """NUL 제거, 줄바꿈 정규화. 빈 문자열은 None."""
    if not body:
        return None
    cleaned = body.replace("\x00", "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    return cleaned.strip() or None
