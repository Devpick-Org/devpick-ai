"""모의면접 서비스 — Bedrock 호출은 모킹하여 fallback / 정상 케이스 검증."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.schemas.job_ai import (
    MockInterviewFinalizeRequest,
    MockInterviewPlan,
    MockInterviewPlanRequest,
    MockInterviewQuestionPlanItem,
    MockInterviewTurnRequest,
)
from app.services.job_ai_service import JobAiService


def _service() -> JobAiService:
    with patch("boto3.client"):
        return JobAiService(aws_region="us-east-1", model="anthropic.test")


def _base_plan() -> MockInterviewPlan:
    return MockInterviewPlan(
        questions=[
            MockInterviewQuestionPlanItem(
                questionNo=i + 1,
                phase="WARM_UP" if i < 2 else "PROJECT",
                topic="topic",
                prompt="prompt",
                keywords=[],
            )
            for i in range(15)
        ],
        coreCsTopics=["Browser Internals"],
        extendedCsTopics=["SEO"],
        jdGapKeywords=["sentry"],
        domainLabel="FRONTEND",
    )


def _bedrock_response(payload: dict) -> dict:
    return {
        "output": {
            "message": {"content": [{"text": json.dumps(payload, ensure_ascii=False)}]}
        }
    }


def test_plan_mock_interview_returns_base_plan_on_failure() -> None:
    svc = _service()
    mock_client = MagicMock()
    mock_client.converse.side_effect = RuntimeError("boom")
    svc._client = mock_client  # type: ignore[attr-defined]

    base = _base_plan()
    refined = svc.plan_mock_interview(
        MockInterviewPlanRequest(job_title="FE", base_plan=base)
    )
    assert refined == base


def test_plan_mock_interview_uses_refined_when_valid() -> None:
    svc = _service()
    refined_plan = _base_plan().model_copy()
    refined_plan.questions[0].prompt = "다듬어진 질문입니다."
    payload = json.loads(refined_plan.model_dump_json())

    mock_client = MagicMock()
    mock_client.converse.return_value = _bedrock_response(payload)
    svc._client = mock_client  # type: ignore[attr-defined]

    out = svc.plan_mock_interview(
        MockInterviewPlanRequest(job_title="FE", base_plan=_base_plan())
    )
    assert out.questions[0].prompt == "다듬어진 질문입니다."
    assert len(out.questions) == 15


def test_evaluate_mock_turn_returns_safe_default_on_invalid_json() -> None:
    svc = _service()
    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": "not json"}]}}
    }
    svc._client = mock_client  # type: ignore[attr-defined]

    out = svc.evaluate_mock_turn(
        MockInterviewTurnRequest(
            question_no=1,
            phase="WARM_UP",
            answer="짧은 답",
        )
    )
    assert out.rating == "OK"
    assert out.decision == "next"


def test_evaluate_mock_turn_parses_valid_payload() -> None:
    svc = _service()
    payload = {
        "rating": "GOOD",
        "evaluator_comment": "잘 답변하셨어요.",
        "decision": "follow_up",
        "follow_up_question": "조금 더 구체적인 예시는요?",
    }
    mock_client = MagicMock()
    mock_client.converse.return_value = _bedrock_response(payload)
    svc._client = mock_client  # type: ignore[attr-defined]

    out = svc.evaluate_mock_turn(
        MockInterviewTurnRequest(
            question_no=1,
            phase="WARM_UP",
            answer="자기소개입니다. 백엔드 개발 5년 차입니다.",
        )
    )
    assert out.rating == "GOOD"
    assert out.decision == "follow_up"
    assert out.follow_up_question


def test_finalize_falls_back_when_bedrock_fails() -> None:
    svc = _service()
    mock_client = MagicMock()
    mock_client.converse.side_effect = RuntimeError("boom")
    svc._client = mock_client  # type: ignore[attr-defined]

    out = svc.finalize_mock_interview(
        MockInterviewFinalizeRequest(plan=_base_plan(), turns=[])
    )
    assert out.notice == "fallback"
    assert len(out.perQuestion) == 15
    assert all(p.passed for p in out.perQuestion)


def test_resolve_model_key_defaults() -> None:
    svc = _service()
    assert svc._resolve_model_key("balanced") == "anthropic.test"
    assert svc._resolve_model_key("BALANCED") == "anthropic.test"
    assert svc._resolve_model_key("unknown") == "anthropic.test"
    assert svc._resolve_model_key("fast")  # 폴백 모델 id 가 비어있지 않다
    assert svc._resolve_model_key("deep")
