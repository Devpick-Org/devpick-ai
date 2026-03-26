"""build_user_prompt() 포맷 검증 테스트 (DP-260)."""

from __future__ import annotations

from app.core.prompts.insight import build_user_prompt
from app.schemas.insight import ActivityData, DailyActivity, TagActivity, TagCount


def _base_activities(**kwargs) -> ActivityData:
    defaults = {
        "contents_read": 0,
        "questions_created": 0,
        "scraps_count": 0,
    }
    defaults.update(kwargs)
    return ActivityData(**defaults)


def test_period_appears_in_prompt() -> None:
    prompt = build_user_prompt(
        activities=_base_activities(),
        ai_events={},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "2026-03-17" in prompt
    assert "2026-03-23" in prompt


def test_basic_activity_counts_appear() -> None:
    prompt = build_user_prompt(
        activities=_base_activities(contents_read=5, questions_created=2, scraps_count=3),
        ai_events={},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "5" in prompt
    assert "2" in prompt
    assert "3" in prompt


def test_read_summaries_section_present() -> None:
    prompt = build_user_prompt(
        activities=_base_activities(),
        ai_events={},
        read_summaries=[{"one_line_summary": "Redis TTL 관리 전략 분석"}],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "읽은 글" in prompt
    assert "Redis TTL 관리 전략 분석" in prompt


def test_read_summaries_empty_shows_none() -> None:
    prompt = build_user_prompt(
        activities=_base_activities(),
        ai_events={},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "읽은 글" in prompt
    assert "없음" in prompt


def test_scrapped_summaries_in_separate_section() -> None:
    prompt = build_user_prompt(
        activities=_base_activities(),
        ai_events={},
        read_summaries=[{"one_line_summary": "읽은 글"}],
        scrapped_summaries=[{"one_line_summary": "스크랩한 글"}],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "스크랩한 글" in prompt
    assert "읽은 글" in prompt
    # 스크랩 섹션이 별도 섹션으로 존재
    read_pos = prompt.index("이번 주 읽은 글")
    scrap_pos = prompt.index("스크랩한 글")
    assert scrap_pos > read_pos


def test_scrapped_summaries_empty_shows_none() -> None:
    prompt = build_user_prompt(
        activities=_base_activities(),
        ai_events={},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    # 스크랩 섹션도 존재 (없음으로 표시)
    assert "스크랩한 글" in prompt


def test_question_texts_section_present() -> None:
    prompt = build_user_prompt(
        activities=_base_activities(),
        ai_events={},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=["Redis TTL을 동적으로 설정하는 방법은?"],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "작성한 질문" in prompt
    assert "Redis TTL을 동적으로 설정하는 방법은?" in prompt


def test_question_texts_empty_shows_none() -> None:
    prompt = build_user_prompt(
        activities=_base_activities(),
        ai_events={},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "작성한 질문" in prompt
    assert "없음" in prompt


def test_daily_activities_section_present() -> None:
    activities = _base_activities(
        daily_activities=[
            DailyActivity(day_of_week="MON", count=3),
            DailyActivity(day_of_week="TUE", count=1),
        ]
    )
    prompt = build_user_prompt(
        activities=activities,
        ai_events={},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "요일별 활동" in prompt
    assert "MON" in prompt
    assert "TUE" in prompt


def test_tag_activities_section_present() -> None:
    activities = _base_activities(
        tag_activities=[
            TagActivity(tag_name="Spring Boot", count=5),
            TagActivity(tag_name="Redis", count=3),
        ]
    )
    prompt = build_user_prompt(
        activities=activities,
        ai_events={},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "태그" in prompt
    assert "Spring Boot" in prompt
    assert "Redis" in prompt


def test_top_tags_fallback_when_no_tag_activities() -> None:
    activities = _base_activities(
        top_tags=[TagCount(tag="Docker", count=2)],
    )
    prompt = build_user_prompt(
        activities=activities,
        ai_events={},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "Docker" in prompt


def test_ai_events_section_present() -> None:
    prompt = build_user_prompt(
        activities=_base_activities(),
        ai_events={"refine": 2, "answer": 1, "similar": 3},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "AI 기능" in prompt
    assert "2" in prompt
    assert "1" in prompt
    assert "3" in prompt


def test_zero_activity_prompt_is_valid() -> None:
    """활동이 전혀 없는 경우에도 정상 포맷 생성."""
    prompt = build_user_prompt(
        activities=ActivityData(),
        ai_events={},
        read_summaries=[],
        scrapped_summaries=[],
        question_texts=[],
        week_start="2026-03-17",
        week_end="2026-03-23",
    )
    assert "기본 활동" in prompt
    assert "없음" in prompt
