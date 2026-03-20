"""answer 프롬프트 빌더 단위 테스트 (DP-234)."""

from __future__ import annotations

import pytest

from app.core.prompts.answer import build_user_prompt


def test_prompt_always_includes_question() -> None:
    result = build_user_prompt(
        refined_title="useEffect 무한 렌더링 원인",
        refined_content="dependency array를 비워두면 계속 렌더링됩니다",
    )
    assert "## 질문" in result
    assert "useEffect 무한 렌더링 원인" in result
    assert "dependency array를 비워두면" in result


def test_prompt_with_article_chunks() -> None:
    result = build_user_prompt(
        refined_title="제목",
        refined_content="본문",
        article_chunks=["React 렌더링 사이클은...", "useEffect는..."],
    )
    assert "## 관련 아티클" in result
    assert "React 렌더링 사이클은" in result


def test_prompt_without_article_chunks() -> None:
    result = build_user_prompt(
        refined_title="제목",
        refined_content="본문",
    )
    assert "## 관련 아티클" not in result


def test_prompt_with_rag_chunks() -> None:
    result = build_user_prompt(
        refined_title="제목",
        refined_content="본문",
        rag_chunks=["[출처: blog_001]\nReact useState 훅은..."],
    )
    assert "## 참고 문서" in result
    assert "blog_001" in result
    assert "React useState" in result


def test_prompt_without_rag_chunks() -> None:
    result = build_user_prompt(
        refined_title="제목",
        refined_content="본문",
    )
    assert "## 참고 문서" not in result


def test_prompt_with_both_chunks() -> None:
    result = build_user_prompt(
        refined_title="제목",
        refined_content="본문",
        article_chunks=["아티클 내용"],
        rag_chunks=["[출처: blog_001]\nRAG 내용"],
    )
    assert "## 관련 아티클" in result
    assert "## 참고 문서" in result
    assert "아티클 내용" in result
    assert "RAG 내용" in result


def test_prompt_with_no_chunks() -> None:
    result = build_user_prompt(
        refined_title="제목",
        refined_content="본문",
    )
    assert "## 관련 아티클" not in result
    assert "## 참고 문서" not in result


def test_prompt_with_original_question() -> None:
    result = build_user_prompt(
        refined_title="개선된 제목",
        refined_content="개선된 본문",
        original_title="원본 제목",
        original_content="원본 본문",
    )
    assert "## 원본 질문" in result
    assert "원본 제목" in result
    assert "원본 본문" in result


def test_prompt_without_original_question() -> None:
    result = build_user_prompt(
        refined_title="제목",
        refined_content="본문",
    )
    assert "## 원본 질문" not in result


def test_prompt_with_suggested_tags() -> None:
    result = build_user_prompt(
        refined_title="제목",
        refined_content="본문",
        suggested_tags=["React", "useEffect", "렌더링"],
    )
    assert "## 관련 기술 태그" in result
    assert "React" in result
    assert "useEffect" in result


def test_prompt_without_suggested_tags() -> None:
    result = build_user_prompt(
        refined_title="제목",
        refined_content="본문",
    )
    assert "## 관련 기술 태그" not in result


def test_prompt_empty_refined_title_raises() -> None:
    with pytest.raises(ValueError, match="개선된 질문 제목과 본문은 필수"):
        build_user_prompt(refined_title="", refined_content="본문")


def test_prompt_empty_refined_content_raises() -> None:
    with pytest.raises(ValueError, match="개선된 질문 제목과 본문은 필수"):
        build_user_prompt(refined_title="제목", refined_content="")


def test_prompt_section_order() -> None:
    """섹션 순서: 관련 아티클 → 참고 문서 → 원본 질문 → 관련 기술 태그 → 질문."""
    result = build_user_prompt(
        refined_title="제목",
        refined_content="본문",
        article_chunks=["아티클"],
        rag_chunks=["RAG"],
        original_title="원본 제목",
        original_content="원본 본문",
        suggested_tags=["태그"],
    )
    idx_article = result.index("## 관련 아티클")
    idx_rag = result.index("## 참고 문서")
    idx_original = result.index("## 원본 질문")
    idx_tags = result.index("## 관련 기술 태그")
    idx_question = result.index("## 질문")

    assert idx_article < idx_rag < idx_original < idx_tags < idx_question
