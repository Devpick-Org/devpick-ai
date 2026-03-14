"""PreprocessService 단위 테스트 (DP-216)."""

from __future__ import annotations

import pytest

from app.services.preprocess_service import PreprocessService


@pytest.fixture
def svc() -> PreprocessService:
    return PreprocessService()


def test_script_style_removed(svc: PreprocessService) -> None:
    html = "<div><script>alert('xss')</script><p>본문입니다.</p></div>"
    result = svc.preprocess(html)
    assert "alert" not in result
    assert "본문입니다" in result


def test_style_removed(svc: PreprocessService) -> None:
    html = "<div><style>body { color: red; }</style><p>내용</p></div>"
    result = svc.preprocess(html)
    assert "color" not in result
    assert "내용" in result


def test_nav_footer_removed(svc: PreprocessService) -> None:
    html = "<nav>메뉴</nav><main><p>기사 본문</p></main><footer>푸터</footer>"
    result = svc.preprocess(html)
    assert "메뉴" not in result
    assert "푸터" not in result
    assert "기사 본문" in result


def test_pre_code_preserved(svc: PreprocessService) -> None:
    html = "<div><pre><code>def foo():\n    return 42\n</code></pre></div>"
    result = svc.preprocess(html)
    assert "```" in result
    assert "def foo():" in result
    assert "return 42" in result


def test_heading_conversion(svc: PreprocessService) -> None:
    html = "<article><h2>제목입니다</h2><p>내용</p></article>"
    result = svc.preprocess(html)
    assert "## 제목입니다" in result


def test_all_heading_levels(svc: PreprocessService) -> None:
    html = "<h1>H1</h1><h3>H3</h3><h6>H6</h6>"
    result = svc.preprocess(html)
    assert "# H1" in result
    assert "### H3" in result
    assert "###### H6" in result


def test_list_conversion(svc: PreprocessService) -> None:
    html = "<ul><li>항목 A</li><li>항목 B</li></ul>"
    result = svc.preprocess(html)
    assert "- 항목 A" in result
    assert "- 항목 B" in result


def test_html_entity_unescaped(svc: PreprocessService) -> None:
    html = "<p>A &amp; B &lt; C &gt; D</p>"
    result = svc.preprocess(html)
    assert "A & B < C > D" in result


def test_empty_body_raises(svc: PreprocessService) -> None:
    html = "<div><script>var x = 1;</script><style>a{}</style></div>"
    with pytest.raises(ValueError, match="요약 불가"):
        svc.preprocess(html)


def test_boilerplate_line_removed(svc: PreprocessService) -> None:
    html = "<div><p>실제 본문 내용이 들어갑니다.</p><p>공유하기</p></div>"
    result = svc.preprocess(html)
    # "공유하기" 가 단독 라인으로 제거되어야 함
    lines = [line.strip() for line in result.splitlines()]
    assert "공유하기" not in lines
    assert "실제 본문 내용이 들어갑니다." in result


def test_inline_code(svc: PreprocessService) -> None:
    html = "<p>함수 <code>func()</code>를 호출하세요.</p>"
    result = svc.preprocess(html)
    assert "`func()`" in result


def test_blockquote(svc: PreprocessService) -> None:
    html = "<blockquote>인용 문장입니다.</blockquote><p>본문</p>"
    result = svc.preprocess(html)
    assert "> 인용 문장입니다." in result


def test_br_converted_to_newline(svc: PreprocessService) -> None:
    html = "<p>첫째 줄<br/>둘째 줄</p>"
    result = svc.preprocess(html)
    assert "첫째 줄" in result
    assert "둘째 줄" in result
    # br이 줄바꿈으로 변환됐는지 확인
    assert "\n" in result


def test_code_block_whitespace_preserved(svc: PreprocessService) -> None:
    """코드블록 내부 공백은 정규화 대상에서 제외."""
    code = "if x:\n    pass\n    # indent"
    html = f"<pre>{code}</pre><p>설명</p>"
    result = svc.preprocess(html)
    assert "    pass" in result
    assert "    # indent" in result


def test_noscript_removed(svc: PreprocessService) -> None:
    html = "<noscript>JS 필요</noscript><p>메인 콘텐츠</p>"
    result = svc.preprocess(html)
    assert "JS 필요" not in result
    assert "메인 콘텐츠" in result


def test_img_alt_preserved(svc: PreprocessService) -> None:
    html = '<p>설명<img src="diagram.png" alt="시스템 구조도"/>입니다.</p>'
    result = svc.preprocess(html)
    assert "[이미지: 시스템 구조도]" in result


def test_img_without_alt_ignored(svc: PreprocessService) -> None:
    html = '<p>본문<img src="spacer.gif"/>내용</p>'
    result = svc.preprocess(html)
    assert "[이미지" not in result
    assert "본문" in result
