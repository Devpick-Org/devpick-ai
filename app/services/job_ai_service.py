"""채용 JD 파싱·면접 Q&A·부족 역량 로드맵 — Bedrock Converse (Epic G)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from app.core.exceptions import AIInternalError, AITimeoutError, AIUpstreamError
from app.schemas.job_ai import (
    InterviewQaRequest,
    ParseJdRequest,
    ParseJdResponse,
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


class JobAiService:
    """JD 파싱·면접 Q&A·skill-gap을 동일 Bedrock 모델로 호출(트렌드·인사이트와 동일 Sonnet 4.6 권장)."""

    def __init__(self, aws_region: str, model: str) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=aws_region,
            config=Config(read_timeout=300, retries={"max_attempts": 0}),
        )
        self._model = model

    def parse_jd(self, body: ParseJdRequest) -> ParseJdResponse:
        text = body.raw_jd_text.strip()
        if len(text) < 40 and not any(ch.isalpha() for ch in text):
            return ParseJdResponse(skip_reason="image_jd")
        sys = (
            "You extract job requirements from Korean or English job descriptions. "
            "Return ONLY valid JSON with keys: required_skills (array of short tech/skill names), "
            "preferred_skills (array), skip_reason (null or string). "
            "Classify obvious must-haves as required_skills and nice-to-have as preferred_skills. "
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
