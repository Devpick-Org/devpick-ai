from app.collectors.velog_body import sanitize_velog_body


def test_sanitize_removes_nul() -> None:
    assert sanitize_velog_body("a\x00b") == "ab"


def test_sanitize_normalizes_line_endings() -> None:
    assert sanitize_velog_body("a\r\nb\rc") == "a\nb\nc"


def test_sanitize_empty_to_none() -> None:
    assert sanitize_velog_body("   ") is None
    assert sanitize_velog_body(None) is None
