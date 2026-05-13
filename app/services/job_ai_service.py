"""채용 JD 파싱·면접 Q&A·부족 역량 로드맵 — Bedrock Converse (Epic G)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from app.core.exceptions import AIInternalError, AITimeoutError, AIUpstreamError
from app.schemas.job_ai import (
    InterviewQaRequest,
    MockInterviewFinalizeRequest,
    MockInterviewFinalizeResponse,
    MockInterviewPerQuestionFeedback,
    MockInterviewPlan,
    MockInterviewPlanRequest,
    MockInterviewScoreSet,
    MockInterviewTurnRequest,
    MockInterviewTurnResponse,
    ParseJdRequest,
    ParseJdResponse,
    ResumeEnrichRequest,
    ResumeParseRequest,
    SkillGapRequest,
    SkillGapResponse,
)

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_json_object(text: str) -> dict[str, Any]:
    if not text or not text.strip():
        raise AIInternalError("empty_model_output")
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    m = _JSON_FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError as exc:
            raise AIInternalError("json_fence_parse_failed") from exc
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIInternalError("json_slice_parse_failed") from exc
    raise AIInternalError("no_json_in_model_output")


def _normalize_resume_candidate(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AIInternalError("resume_parse_invalid_root")
    if "basicInfo" not in data or not isinstance(data.get("basicInfo"), dict):
        data["basicInfo"] = {
            "name": "",
            "jobTitle": "",
            "careerYears": 0,
            "location": "",
        }
    if "techStack" not in data or not isinstance(data["techStack"], list):
        data["techStack"] = []
    if "careers" not in data or not isinstance(data["careers"], list):
        data["careers"] = []
    if "projects" not in data or not isinstance(data["projects"], list):
        data["projects"] = []
    data.setdefault("summary", "")
    if not isinstance(data["summary"], str):
        data["summary"] = str(data["summary"])

    tech_raw = data["techStack"]
    tech: list[str] = []
    seen: set[str] = set()
    for t in tech_raw:
        s = str(t).strip()
        if not s:
            continue
        lk = s.lower()
        if lk in seen:
            continue
        seen.add(lk)
        tech.append(s)
    data["techStack"] = tech

    return data


def _normalize_enrich_patch(raw: dict[str, Any]) -> dict[str, Any]:
    """모델 응답에서 허용 키만 남기고 타입 보정."""
    allowed_keys = frozenset({"summary", "careers", "projects", "techStack"})
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out

    summary = raw.get("summary")
    if isinstance(summary, str):
        out["summary"] = summary.strip()

    careers = raw.get("careers")
    if isinstance(careers, list):
        careers_out: list[dict[str, str]] = []
        for item in careers:
            if isinstance(item, dict):
                careers_out.append(
                    {
                        "company": _str_clean(item.get("company")),
                        "role": _str_clean(item.get("role")),
                        "period": _str_clean(item.get("period")),
                        "description": _str_clean(item.get("description")),
                    }
                )
        out["careers"] = careers_out

    projects = raw.get("projects")
    if isinstance(projects, list):
        projects_out: list[dict[str, Any]] = []
        for item in projects:
            if isinstance(item, dict):
                ts_raw = item.get("techStack") or item.get("tech_stack")
                ts_items: list[str] = []
                if isinstance(ts_raw, list):
                    seen_t = set()
                    for t in ts_raw:
                        s = str(t).strip()
                        if not s:
                            continue
                        lk = s.lower()
                        if lk in seen_t:
                            continue
                        seen_t.add(lk)
                        ts_items.append(s)
                projects_out.append(
                    {
                        "name": _str_clean(item.get("name")),
                        "period": _str_clean(item.get("period")),
                        "role": _str_clean(item.get("role")),
                        "description": _str_clean(item.get("description")),
                        "achievements": _str_clean(item.get("achievements")),
                        "techStack": ts_items,
                    }
                )
        out["projects"] = projects_out

    tech_stack = raw.get("techStack") or raw.get("tech_stack")
    if isinstance(tech_stack, list):
        tech: list[str] = []
        seen: set[str] = set()
        for t in tech_stack:
            s = str(t).strip()
            if not s:
                continue
            lk = s.lower()
            if lk in seen:
                continue
            seen.add(lk)
            tech.append(s)
        out["techStack"] = tech

    _ = allowed_keys  # 허용 키 명시
    return out


def _str_clean(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


class JobAiService:
    """JD 파싱·면접 Q&A·skill-gap을 동일 Bedrock 모델로 호출(트렌드·인사이트와 동일 Sonnet 4.6 권장)."""

    # 사용자에게 노출되는 모델 키 → Bedrock model id 매핑.
    # `MOCK_INTERVIEW_MODEL_*` 환경변수로 덮어쓸 수 있다.
    _MODEL_KEY_ENV: dict[str, str] = {
        "fast": "MOCK_INTERVIEW_MODEL_FAST",
        "balanced": "MOCK_INTERVIEW_MODEL_BALANCED",
        "deep": "MOCK_INTERVIEW_MODEL_DEEP",
    }
    _MODEL_KEY_FALLBACK: dict[str, str] = {
        "fast": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        "balanced": "global.anthropic.claude-sonnet-4-6",
        "deep": "global.anthropic.claude-opus-4-1-20250805-v1:0",
    }

    def __init__(self, aws_region: str, model: str) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=aws_region,
            config=Config(read_timeout=300, retries={"max_attempts": 0}),
        )
        self._model = model
        self._aws_region = aws_region

    def _resolve_model_key(self, key: str | None) -> str:
        """모의면접용 모델 키를 실제 Bedrock model id로 매핑한다.

        - 알 수 없는 키는 기본 모델로 폴백한다.
        - balanced/fast/deep 모두 환경변수가 있으면 그 값을 우선한다.
        """
        norm = (key or "").strip().lower()
        if norm not in self._MODEL_KEY_ENV:
            return self._model
        env_var = self._MODEL_KEY_ENV[norm]
        env_value = os.getenv(env_var)
        if env_value:
            return env_value
        # balanced 는 Job AI 기본 모델을 그대로 사용해 비용/거버넌스를 단순화한다.
        if norm == "balanced":
            return self._model
        return self._MODEL_KEY_FALLBACK[norm]

    def parse_jd(self, body: ParseJdRequest) -> ParseJdResponse:
        text = body.raw_jd_text.strip()
        if len(text) < 40 and not any(ch.isalpha() for ch in text):
            return ParseJdResponse(skip_reason="image_jd")
        sys = (
            "You extract job requirements from Korean or English job descriptions. "
            "Return ONLY valid JSON with keys: required_skills (array of short tech/skill names), "
            "preferred_skills (array), skip_reason (null or string). "
            "Classify obvious must-haves as required_skills and nice-to-have as preferred_skills. "
            "Skills that appear ONLY in 우대/preferred sections (even if wording is soft like “경험 있으신 분”) "
            "must go to preferred_skills, not required_skills. "
            "Include concrete tech tokens (languages, frameworks, clouds, databases, CI, test tools).\n"
            "If the text is not a real JD (e.g. only an image placeholder), set skip_reason to image_jd."
        )
        user = f"JD text:\n{text[:120_000]}"
        raw = self._converse_text(self._model, sys, user, max_tokens=1024)
        data = _extract_json_object(raw)
        return ParseJdResponse.model_validate(data)

    def interview_qa(self, body: InterviewQaRequest) -> dict[str, Any]:
        sys = (
            "You are an interview coach. Return ONLY valid JSON with key 'categories' — "
            "an array of 4 objects with keys: title (one of 자기소개, 프로젝트, 기술, 커뮤니케이션), "
            "items: array of {question, answer, followUps: string array (1-3 items)}. "
            "Provide exactly 3 questions for the first three categories and 1 for 커뮤니케이션 (10 total). "
            "Answers should be concise Korean, tailored to the candidate resume JSON and the job skills."
        )
        user = json.dumps(
            {
                "job_title": body.job_title,
                "company_name": body.company_name,
                "required_skills": body.required_skills,
                "preferred_skills": body.preferred_skills,
                "resume": body.resume_json[:80_000],
            },
            ensure_ascii=False,
        )
        raw = self._converse_text(self._model, sys, user, max_tokens=8192)
        return _extract_json_object(raw)

    def skill_gap(self, body: SkillGapRequest) -> SkillGapResponse:
        sys = (
            "Return ONLY valid JSON with key: roadmap — an array of 5-8 short Korean learning steps "
            "ordered for someone who must learn the missing_skills for the given job. "
            "No other keys."
        )
        user = json.dumps(
            {
                "missing_skills": body.missing_skills,
                "job_title": body.job_title,
                "company_name": body.company_name,
            },
            ensure_ascii=False,
        )
        raw = self._converse_text(self._model, sys, user, max_tokens=2048)
        data = _extract_json_object(raw)
        return SkillGapResponse.model_validate(data)

    def parse_candidate_resume(self, body: ResumeParseRequest) -> dict[str, Any]:
        txt = body.text.strip()[:120_000]
        sys = (
            "You normalize Korean or English resumes into structured data for a SaaS CV editor. "
            "Return ONLY valid JSON using camelCase keys: "
            "fileName optional string display name without folders, "
            "basicInfo{name,jobTitle,careerYears non-negative integer,location}, "
            "summary Korean text (empty string if unsure), techStack[], "
            "careers{array of company,role,period,description}, "
            "projects{array of name,period,role,techStack[],description,achievements}. "
            "Use canonical tech spellings (Node.js, Spring Boot, TypeScript, PostgreSQL). "
            "Do NOT use markdown fences. Do NOT add commentary outside JSON."
        )
        payload: dict[str, Any] = {
            "file_name": body.file_name,
            "resume_text_head": txt[:24_000],
            "resume_text_tail": txt[-8000:] if len(txt) > 24_000 else "",
        }
        if body.profile_hint:
            payload["profile_hint"] = body.profile_hint[:6000]

        user = json.dumps(payload, ensure_ascii=False)
        raw = self._converse_text(self._model, sys, user, max_tokens=8192)
        extracted = _extract_json_object(raw)
        return _normalize_resume_candidate(extracted)

    def enrich_candidate_resume(self, body: ResumeEnrichRequest) -> dict[str, Any]:
        """1차 결과를 알려 준 상태에서 빈 필드 후보만 채운 패치 JSON을 반환."""
        txt = body.text.strip()[:120_000]
        partial: dict[str, Any]
        if isinstance(body.partial_resume, str):
            try:
                partial = json.loads(body.partial_resume)
            except json.JSONDecodeError as exc:
                raise AIInternalError("enrich_partial_not_json") from exc
            if not isinstance(partial, dict):
                raise AIInternalError("enrich_partial_invalid")
        elif isinstance(body.partial_resume, dict):
            partial = body.partial_resume
        else:
            raise AIInternalError("enrich_partial_invalid")

        sys = (
            "You help fill MISSING sections of a resume for a SaaS CV editor draft. "
            "The user already parsed the document once; your output is SECOND-PASS PATCH only.\n"
            "Return ONLY valid JSON with ZERO or more of these camelCase keys: "
            "summary (Korean prose, 3-5 sentences as one string), careers (array), projects (array), "
            "techStack (array). Do NOT repeat basicInfo, fileName, uploadedAt.\n"
            "STRICT FACTUAL RULES:\n"
            "- Never invent employers, titles, periods, counts, certifications, degrees, awards, URLs, patents. "
            "If the source text shows no wording for something, omit it or leave that field empty.\n"
            "- You may reorganize wording from the SAME document into structured careers/projects/description; "
            "do NOT add plausible fiction.\n"
            "- If unsure, prefer empty arrays and empty summary string.\n"
            "- techStack: only technologies explicitly readable in resume_text.\n"
            "careers[].{company,role,period,description} and "
            "projects[].{name,period,role,description,achievements,string techStack[]} same schema as CV tools.\n"
            "already_parsed shows what PASS1 extracted—only IMPROVE fields that are visibly empty/useless vs text.\n"
            "No markdown. No prose outside JSON."
        )
        payload: dict[str, Any] = {
            "file_name": body.file_name,
            "resume_text_head": txt[:28_000],
            "resume_text_tail": txt[-12_000] if len(txt) > 28_000 else "",
            "already_parsed": partial,
            "constraints": (
                "If already_parsed.careers is non-empty array, omit careers entirely or send []. "
                "If already_parsed.projects is non-empty array, omit projects entirely or send []. "
                "Fill summary only when already_parsed.summary is empty OR len <40 characters—else omit summary key."
            ),
        }
        user = json.dumps(payload, ensure_ascii=False)
        raw = self._converse_text(self._model, sys, user, max_tokens=8192)
        extracted = _extract_json_object(raw)
        return _normalize_enrich_patch(extracted)

    # ──────────────────────────────────
    # Mock Interview (채팅형 모의면접)
    # ──────────────────────────────────

    def plan_mock_interview(self, body: MockInterviewPlanRequest) -> MockInterviewPlan:
        """이력서·JD·기준 플랜을 받아 15문항 채팅형 면접 플랜을 보강한다.

        Spring 쪽이 이미 균형 잡힌 base_plan을 만들어 보내므로, 모델은
        prompt 문장만 자연스럽게 다듬고 keywords/jdGapKeywords를 정제한다.
        오류 시 base_plan을 그대로 돌려 안전장치 역할을 한다.
        """
        sys = (
            "You are a senior software-engineering interviewer. "
            "You receive a base interview plan (Korean) of exactly 15 questions in five phases "
            "(WARM_UP 2, PROJECT 4, DOMAIN 4, CS_INFRA 4, BEHAVIORAL 1). "
            "Refine each question prompt so it is natural Korean, concise (under 220 chars), "
            "and tailored to the resume and JD. Keep questionNo/phase/topic as-is and keep array length 15. "
            "Return ONLY valid JSON matching the input schema with keys: "
            "questions, coreCsTopics, extendedCsTopics, jdGapKeywords, domainLabel."
        )
        user = json.dumps(
            {
                "job_title": body.job_title,
                "company_name": body.company_name,
                "job_category": body.job_category,
                "required_skills": body.required_skills,
                "preferred_skills": body.preferred_skills,
                "resume": (body.resume_json or "")[:60_000],
                "base_plan": body.base_plan.model_dump(),
            },
            ensure_ascii=False,
        )
        try:
            model = self._resolve_model_key(body.model_key)
            raw = self._converse_text(model, sys, user, max_tokens=4096)
            data = _extract_json_object(raw)
            plan = MockInterviewPlan.model_validate(data)
            if len(plan.questions) == 15:
                return plan
        except Exception as exc:  # noqa: BLE001
            logger.warning("mock_interview plan refine failed: %s", exc)
        return body.base_plan

    def evaluate_mock_turn(
        self, body: MockInterviewTurnRequest
    ) -> MockInterviewTurnResponse:
        """현재 답변에 대한 평가/꼬리/재답변/다음 결정.

        - rating ∈ {GOOD, OK, WEAK}
        - decision ∈ {follow_up, retry, next}
        """
        sys = (
            "You are a fair Korean technical interviewer. Evaluate the candidate's answer for ONE question, "
            "then decide whether to ask a follow-up, request a retry, or move on. "
            "Return ONLY valid JSON with keys: "
            "rating (GOOD/OK/WEAK), evaluator_comment (Korean, <=2 sentences, focused on what was actually said), "
            "decision (follow_up/retry/next), follow_up_question (Korean, optional), "
            "retry_hint (Korean, optional, only when WEAK and recoverable), "
            "next_question_prompt (optional, leave null unless you must rephrase the next prompt). "
            "Rules: "
            "- Do NOT criticize topics that were not asked. "
            "- If answer is too short (<25 chars) or unrelated, set rating WEAK and decision retry. "
            "- If decision is follow_up, ALWAYS provide follow_up_question. "
            "- Never assume facts not in the answer. "
            "- Keep all Korean text natural and concise."
        )
        payload = body.model_dump()
        # 길이 보호
        payload["transcript"] = payload.get("transcript", [])[-10:]
        if len(payload.get("answer", "")) > 8000:
            payload["answer"] = payload["answer"][:8000]
        user = json.dumps(payload, ensure_ascii=False)
        try:
            model = self._resolve_model_key(body.model_key)
            raw = self._converse_text(model, sys, user, max_tokens=1024)
            data = _extract_json_object(raw)
            return MockInterviewTurnResponse.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mock_interview turn eval failed: %s", exc)
            return MockInterviewTurnResponse(
                rating="OK",
                evaluator_comment="AI 평가가 일시적으로 실패했습니다. 다음 질문으로 진행합니다.",
                decision="next",
            )

    def finalize_mock_interview(
        self, body: MockInterviewFinalizeRequest
    ) -> MockInterviewFinalizeResponse:
        """면접 종료 시 5개 영역 점수, 종합 피드백, QA별 모범답안을 생성한다.

        - 답변하지 않은 영역(미질문)은 '부족'으로 평가하지 않는다.
        - 조기 종료 시 진행률에 따라 점수를 보정해야 한다.
        """
        sys = (
            "You generate the final report for a mock interview. Return ONLY valid JSON with keys: "
            "scores (object: framework, design, problemSolving, csInfra, communication; integers 0-100 OR null when uncovered), "
            "overallScore (integer 0-100 or null when no covered area), "
            "summary (Korean 3-4 sentences), strengths (Korean 2-3 items), improvements (Korean 2-3 items), "
            "actionItems (Korean 3-5 items), uncoveredKeywords (string array), "
            "perQuestion (array; for EVERY questionNo 1..15 in plan), "
            "notice (optional). "
            "perQuestion item keys: questionNo, questionSummary (Korean <=40 chars), "
            "answerSummary (Korean <=80 chars), modelAnswer (Korean >=150 chars, concrete examples and tech terms), "
            "whyImportant (Korean <=60 chars), learningDirection (Korean <=80 chars), "
            "references (string[]; up to 2 official-looking URLs), rating (GOOD/OK/WEAK or null when passed), "
            "passed (true if PASS turn). "
            "Rules: only evaluate based on actual answers. If a question was passed or never answered, mark passed=true and "
            "answerSummary='패스'. Do NOT lower scores due to missing questions; instead leave that area null and explain it in summary. "
            "When early_finished is true, dampen scores by coverage proportion."
        )
        payload = body.model_dump()
        # 안전한 길이 — 너무 큰 transcript 차단
        payload["turns"] = payload.get("turns", [])[:120]
        user = json.dumps(payload, ensure_ascii=False)
        try:
            model = self._resolve_model_key(body.model_key)
            raw = self._converse_text(model, sys, user, max_tokens=16384)
            data = _extract_json_object(raw)
            return MockInterviewFinalizeResponse.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mock_interview finalize failed: %s", exc)
            return MockInterviewFinalizeResponse(
                scores=MockInterviewScoreSet(),
                summary="AI 결과 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.",
                uncoveredKeywords=body.plan.jdGapKeywords,
                perQuestion=[
                    MockInterviewPerQuestionFeedback(
                        questionNo=q.questionNo,
                        questionSummary=q.topic[:40],
                        answerSummary="",
                        modelAnswer="",
                        whyImportant="",
                        learningDirection="",
                        references=[],
                        rating=None,
                        passed=True,
                    )
                    for q in body.plan.questions
                ],
                notice="fallback",
            )

    def _converse_text(
        self, model: str, system: str, user: str, max_tokens: int
    ) -> str:
        try:
            response = self._client.converse(
                modelId=model,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
            )
        except ReadTimeoutError as exc:
            raise AITimeoutError("bedrock_timeout") from exc
        except EndpointConnectionError as exc:
            raise AIUpstreamError("bedrock_connection") from exc
        except ClientError as exc:
            raise AIUpstreamError(str(exc)) from exc

        parts = response.get("output", {}).get("message", {}).get("content", [])
        texts = [
            p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p
        ]
        out = "".join(texts).strip()
        if not out:
            raise AIInternalError("empty_bedrock_message")
        return out
