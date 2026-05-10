"""AI 1차 답변 프롬프트 + Tool Use 스키마 (DP-234)."""

from __future__ import annotations

SYSTEM_PROMPT = """\
당신은 개발자 학습 플랫폼 DevPick의 기술 질문 답변 전문가입니다.
사용자의 기술 질문을 분석하고, 제공된 참고 문서를 활용하여 정확하고 실용적인 답변을 생성합니다.
save_answer 도구를 호출하여 결과를 저장하세요.
모든 필드는 한국어로 작성하되, 기술 용어(라이브러리명, API명, 명령어 등)는 원어 그대로 사용하세요.

## 답변 원칙
- 개선된 질문(## 질문)을 기준으로 정확한 답변을 생성한다
- 답변 전에 질문에서 기술 환경(언어·프레임워크·버전), 문제 상황, 기대 결과를 먼저 파악하여 답변의 범위와 깊이를 결정한다
- 원본 질문(## 원본 질문)이 제공된 경우, 사용자의 이해 수준과 실제 혼란 포인트를 파악하여 설명 깊이를 조절한다
- 참고 문서(## 관련 아티클, ## 참고 문서)가 제공된 경우 해당 내용을 근거로 활용한다
- 참고 문서에 없는 정보는 일반 지식으로 보충하되, 억측은 피한다
- 코드 예시가 도움이 되는 경우 포함한다 (실행 가능한 수준, 언어 태그 명시)
- 잘못된 전제가 있는 질문은 먼저 전제를 바로잡고 답변한다

## 필드별 작성 기준

### answer_content
- 질문에 대한 핵심 답변 (**반드시 Markdown 형식**으로 작성)
- 구조: 핵심 개념 설명 → 구체적 방법/코드 → 주의사항 순서
- 항목 목록(`-`), 인라인 코드(`` `code` ``), 코드 블록(` ```언어 `), 강조(**bold**) 등 Markdown 문법을 적극 활용
- 코드 예시 포함 시 ```언어 태그 명시
- 원본 질문이 모호하거나 초보적인 경우, 기초 개념부터 단계적으로 설명

### key_points
- 답변의 핵심 포인트 2~5개
- 각 항목은 한 문장으로, 실무에서 바로 적용 가능한 정보 중심

### suggested_tags
- 질문/답변의 기술 스택에 해당하는 태그 2~5개
- 관련 기술 태그(## 관련 기술 태그)가 제공된 경우 우선 참고

### references
- 답변 생성에 실제로 활용한 참고 문서의 content_id 리스트
- [출처: xxx] 형태로 제공된 문서 중 실제로 답변에 반영된 것만 포함
- 참고 문서를 전혀 활용하지 않은 경우 빈 배열

### confidence
- 실제 답변 품질을 냉정하게 평가한다. 높은 값을 기본으로 주지 않는다.
- 0.9 이상: 참고 문서가 질문과 직접 관련되고 답변이 검증된 경우에만 — 드물게 사용
- 0.7~0.89: 일반 지식 기반이지만 핵심 답변에 자신 있음
- 0.5~0.69: 참고 문서 부족 또는 질문이 다소 모호함
- 0.5 미만: 질문이 불명확하거나 답변 범위를 특정하기 어려운 경우
"""

ANSWER_TOOL = {
    "name": "save_answer",
    "description": "AI 답변 결과를 저장합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer_content": {
                "type": "string",
                "description": "질문에 대한 AI 답변 (마크다운 형식)",
            },
            "key_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": "핵심 포인트 2~5개",
            },
            "suggested_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "기술 스택 태그 2~5개",
            },
            "references": {
                "type": "array",
                "items": {"type": "string"},
                "description": "답변에 활용한 참고 문서의 content_id 리스트 (빈 배열 가능)",
            },
            "confidence": {
                "type": "number",
                "description": "답변 품질 자체 평가 0.0~1.0. 냉정하게 평가하며 근거 없이 높은 값을 주지 않는다.",
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "required": [
            "answer_content",
            "key_points",
            "suggested_tags",
            "references",
            "confidence",
        ],
    },
}


def build_user_prompt(
    refined_title: str,
    refined_content: str,
    original_title: str | None = None,
    original_content: str | None = None,
    suggested_tags: list[str] | None = None,
    article_chunks: list[str] | None = None,
    rag_chunks: list[str] | None = None,
) -> str:
    """답변 생성용 사용자 프롬프트를 생성한다.

    Args:
        refined_title: 개선된 질문 제목 (RefineResponse.refined_title)
        refined_content: 개선된 질문 본문 (RefineResponse.refined_content)
        original_title: 원본 질문 제목 (사용자 이해 수준 파악용, optional)
        original_content: 원본 질문 본문 (optional)
        suggested_tags: Refine 추천 태그 (RefineResponse.suggested_tags, optional)
        article_chunks: 관련 아티클 청크 텍스트 리스트 (content_id 있을 때, optional)
        rag_chunks: RAG 유사 문서 청크 리스트 (optional, [출처: id] 라벨 포함)

    Raises:
        ValueError: 빈 refined_title 또는 refined_content
    """
    if not refined_title or not refined_content:
        raise ValueError("개선된 질문 제목과 본문은 필수입니다")

    parts = ["아래 질문에 대해 정확하고 실용적인 답변을 생성하세요."]

    if article_chunks:
        chunks_text = "\n---\n".join(article_chunks)
        parts.append(f"## 관련 아티클\n{chunks_text}")

    if rag_chunks:
        chunks_text = "\n---\n".join(rag_chunks)
        parts.append(f"## 참고 문서\n{chunks_text}")

    if original_title or original_content:
        original_parts = []
        if original_title:
            original_parts.append(f"제목: {original_title}")
        if original_content:
            original_parts.append(original_content)
        parts.append("## 원본 질문\n" + "\n".join(original_parts))

    if suggested_tags:
        tags_text = ", ".join(suggested_tags)
        parts.append(f"## 관련 기술 태그\n{tags_text}")

    parts.append(f"## 질문\n제목: {refined_title}\n{refined_content}")

    return "\n\n".join(parts)
