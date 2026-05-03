"""Resume enrich 패치 정규화 단위 테스트."""

from __future__ import annotations

from app.services.job_ai_service import _normalize_enrich_patch


def test_normalize_enrich_drops_unknown_top_level_keys():
    raw = {"summary": "요약입니다.", "evil": {}, "bogus": []}
    out = _normalize_enrich_patch(raw)
    assert list(out.keys()) == ["summary"]
    assert out["summary"] == "요약입니다."


def test_normalize_enrich_projects_tech_stack_variants_and_dedupe():
    raw = {
        "projects": [
            {
                "name": " A ",
                "tech_stack": ["Java", "java", "", "Rust"],
                "description": None,
                "role": "",
                "achievements": "",
            }
        ]
    }
    out = _normalize_enrich_patch(raw)
    proj = out["projects"][0]
    assert proj["name"] == "A"
    assert proj["techStack"] == ["Java", "Rust"]


def test_normalize_enrich_empty_dict():
    assert _normalize_enrich_patch({}) == {}
    assert _normalize_enrich_patch({"nested": {"x": 1}}) == {}
