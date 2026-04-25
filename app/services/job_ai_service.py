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


class JobAiService:
    def __init__(
        self,
        aws_region: str,
        model_jd: str,
        model_haiku: str,
        model_sonnet: str,
    ) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=aws_region,
            config=Config(read_timeout=300, retries={"max_attempts": 0}),
        )
        self._jd = model_jd
        self._haiku = model_haiku
        self._sonnet = model_sonnet

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
        raw = self._converse_text(self._jd, sys, user, max_tokens=1024)
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
        raw = self._converse_text(self._sonnet, sys, user, max_tokens=8192)
        return _extract_json_object(raw)

    def skill_gap(self, body: SkillGapRequest) -> SkillGapResponse:
        sys = (
            "Return ONLY valid JSON with keys: roadmap (array of 5-8 short Korean learning steps), "
            "youtube (array of up to 3 objects with title and url — use plausible search-style titles if no real URLs)."
        )
        user = json.dumps(
            {
                "missing_skills": body.missing_skills,
                "job_title": body.job_title,
                "company_name": body.company_name,
            },
            ensure_ascii=False,
        )
        raw = self._converse_text(self._haiku, sys, user, max_tokens=1024)
        data = _extract_json_object(raw)
        return SkillGapResponse.model_validate(data)

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
