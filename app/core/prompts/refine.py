"""AI 질문 개선 프롬프트 + Tool Use 스키마 (DP-231)."""

from __future__ import annotations

SYSTEM_PROMPT = """\
당신은 개발자 학습 플랫폼 DevPick의 질문 개선 전문가입니다.
사용자가 작성한 기술 질문을 분석하여 더 명확하고 답변받기 좋은 질문으로 개선합니다.
save_refined_question 도구를 호출하여 결과를 저장하세요.
모든 필드는 한국어로 작성하되, 기술 용어는 원어 그대로 사용하세요.

## 개선 원칙
- 원래 질문의 의도를 유지하면서 명확하게 재작성
- 모호한 표현을 구체적인 기술 용어로 교체
- 문제 상황, 환경, 기대 결과를 명시하도록 유도
- 참고 문서가 제공된 경우, 해당 문서의 맥락을 활용하여 질문을 구체화

## 필드별 작성 기준

### refined_title
- 핵심 키워드를 포함한 명확한 제목 (1줄, 100자 이내)
- "~하는 방법", "~에서 ~가 발생하는 이유" 같은 구체적 형태

### refined_content
- 질문의 배경, 문제 상황, 시도한 내용, 기대 결과를 포함
- 원본에 없는 정보를 추측해서 추가하지 않음
- 원본의 핵심 내용을 구조화하여 재작성

### suggested_tags
- 질문의 기술 스택/주제에 해당하는 태그 2~5개
- 예: "Redis", "캐시", "Spring Boot"

### confidence
- 0.9 이상: 질문이 이미 명확하고 개선 여지가 적음
- 0.7~0.9: 일반적인 개선
- 0.7 미만: 원본이 매우 모호하거나 정보 부족
"""

REFINE_TOOL = {
    "name": "save_refined_question",
    "description": "개선된 질문 결과를 저장합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "refined_title": {
                "type": "string",
                "description": "개선된 질문 제목 (100자 이내)",
            },
            "refined_content": {
                "type": "string",
                "description": "개선된 질문 본문",
            },
            "suggested_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "추천 태그 2~5개",
            },
            "confidence": {
                "type": "number",
                "description": "개선 품질 자체 평가 0.0~1.0",
            },
        },
        "required": [
            "refined_title",
            "refined_content",
            "suggested_tags",
            "confidence",
        ],
    },
}


def build_user_prompt(
    title: str,
    content: str,
    context_chunks: list[str] | None = None,
) -> str:
    """질문과 컨텍스트 청크로 사용자 프롬프트를 생성한다.

    Args:
        title: 원본 질문 제목
        content: 원본 질문 본문
        context_chunks: MongoDB에서 조회한 아티클 청크 텍스트 리스트 (optional)

    Raises:
        ValueError: 빈 title 또는 content
    """
    if not title or not content:
        raise ValueError("질문 제목과 본문은 필수입니다")

    parts = ["아래 질문을 분석하여 더 명확하고 답변받기 좋은 질문으로 개선하세요."]

    if context_chunks:
        chunks_text = "\n---\n".join(context_chunks)
        parts.append(f"## 참고 문서\n{chunks_text}")

    parts.append(f"## 원본 질문\n제목: {title}\n{content}")

    return "\n\n".join(parts)
