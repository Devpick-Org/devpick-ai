"""4레벨 동시 AI 요약 서비스 — Bedrock Converse API + Tool Use (DP-300)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import boto3
import pydantic
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from app.core.bedrock import to_tool_config
from app.core.exceptions import (
    AIBadRequestError,
    AIInternalError,
    AITimeoutError,
    AIUpstreamError,
)
from app.core.prompts.summary import (
    SUMMARY_ALL_LEVELS_TOOL,
    SYSTEM_PROMPT_ALL_LEVELS,
    build_retry_prompt,
    build_retry_tool,
    build_user_prompt_all_levels,
)
from app.schemas.summary import AllLevelsSummaryResponse

logger = logging.getLogger(__name__)

_TOOL_NAME = "save_all_summaries"


class AllLevelsSummaryService:
    """beginner/junior/mid/senior 4레벨 요약을 Bedrock Claude 1회 호출로 생성한다."""

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        model: str = "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    ) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=aws_region,
            config=Config(read_timeout=300, retries={"max_attempts": 0}),
        )
        self._model = model
        logger.info("AllLevelsSummaryService 초기화 — model=%s", self._model)

    @staticmethod
    def _is_korean_title(title: str) -> bool:
        """제목에 한글이 포함되어 있으면 True를 반환한다."""
        return bool(re.search(r"[\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F]", title))

    def _translate_title(self, title: str) -> str | None:
        """영어 제목을 한국어로 번역한다. 실패 시 None을 반환한다."""
        try:
            response = self._client.converse(
                modelId=self._model,
                system=[
                    {
                        "text": (
                            "기술 아티클 제목을 한국어로 번역하세요. "
                            "번역된 제목만 출력하세요. "
                            "부연 설명, 따옴표, 문장 부호 추가 없이 번역문만 반환하세요."
                        )
                    }
                ],
                messages=[{"role": "user", "content": [{"text": title}]}],
                inferenceConfig={"maxTokens": 100, "temperature": 0.0},
            )
            content = response["output"]["message"]["content"]
            text_block = next((b for b in content if "text" in b), None)
            if text_block:
                return text_block["text"].strip()
            return None
        except Exception:
            logger.warning("제목 번역 실패 (무시): title=%s", title)
            return None

    def summarize_all(
        self,
        content_id: str,
        text: str,
        thumbnail_url: str | None = None,
        title: str | None = None,
        allowed_tags: list[str] | None = None,
    ) -> AllLevelsSummaryResponse:
        """콘텐츠를 4개 레벨로 동시에 요약한다.

        Args:
            content_id: 콘텐츠 식별자
            text: 전처리된 아티클 텍스트 (PreprocessService 출력)
            thumbnail_url: 호출자가 주입하는 썸네일 URL (AI 생성 아님)

        Returns:
            AllLevelsSummaryResponse

        Raises:
            AIBadRequestError: 빈 text
            AITimeoutError: LLM 타임아웃
            AIUpstreamError: LLM 연결 실패 / API 에러 / Rate Limit
            AIInternalError: 파싱 실패 / tool_use 블록 없음
        """
        try:
            user_prompt = build_user_prompt_all_levels(text, allowed_tags)
        except ValueError as exc:
            raise AIBadRequestError(str(exc)) from exc

        try:
            response = self._client.converse(
                modelId=self._model,
                system=[
                    {"text": SYSTEM_PROMPT_ALL_LEVELS},
                    {"cachePoint": {"type": "default"}},
                ],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                toolConfig=to_tool_config(SUMMARY_ALL_LEVELS_TOOL, _TOOL_NAME),
                inferenceConfig={"maxTokens": 8192, "temperature": 0.0},
            )
        except ReadTimeoutError as exc:
            logger.warning("LLM 타임아웃: %s", exc)
            raise AITimeoutError() from exc
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "ThrottlingException":
                logger.warning("LLM Rate Limit: %s", exc)
                raise AIUpstreamError("LLM Rate Limit 초과입니다") from exc
            logger.error("LLM API 오류 (code=%s): %s", code, exc)
            raise AIUpstreamError(f"LLM API 오류: {code}") from exc
        except EndpointConnectionError as exc:
            logger.error("LLM 연결 실패: %s", exc)
            raise AIUpstreamError("LLM 연결에 실패했습니다") from exc

        content = response["output"]["message"]["content"]
        tool_use_block = next((b for b in content if "toolUse" in b), None)
        if not tool_use_block:
            logger.error("LLM 응답에 toolUse 블록이 없습니다. content=%s", content)
            raise AIInternalError("LLM 응답에 tool_use 블록이 없습니다")

        try:
            raw = tool_use_block["toolUse"]["input"]

            missing = [
                lvl for lvl in ("beginner", "junior", "mid", "senior") if lvl not in raw
            ]
            attempt = 0
            max_retries = 4
            while missing and attempt < max_retries:
                attempt += 1
                logger.warning(
                    "누락된 레벨 감지 — 재시도 (%d/%d): %s",
                    attempt,
                    max_retries,
                    missing,
                )
                retry_raw = self._retry_missing_levels(text, missing)
                raw.update(retry_raw)
                missing = [
                    lvl
                    for lvl in ("beginner", "junior", "mid", "senior")
                    if lvl not in raw
                ]

            if missing:
                logger.error("최대 재시도 초과, 레벨 누락: %s", missing)
                raise AIInternalError(f"최대 재시도 초과, 레벨 누락: {missing}")

            for level in ("beginner", "junior", "mid", "senior"):
                if level not in raw:
                    continue
                sections = raw[level].get("core_summary", [])
                if isinstance(sections, list):
                    raw[level]["core_summary"] = "\n\n".join(
                        f"{s['heading']}\n{s['content']}" for s in sections
                    )

            # 영어 제목이면 번역, 한국어이면 None (DP-328)
            translated_title: str | None = None
            if title:
                if self._is_korean_title(title):
                    logger.debug("한국어 제목 — 번역 스킵: %s", title)
                else:
                    translated_title = self._translate_title(title)
                    logger.info("제목 번역 완료: %s → %s", title, translated_title)

            payload = {
                **raw,
                "content_id": content_id,
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                "thumbnail_url": thumbnail_url,
                "title": title,
                "translated_title": translated_title,
            }
            return AllLevelsSummaryResponse.model_validate(payload)
        except pydantic.ValidationError as exc:
            logger.error("AllLevelsSummaryResponse 파싱 실패: %s", exc)
            raise AIInternalError("AI 응답 파싱에 실패했습니다") from exc

    def _retry_missing_levels(self, text: str, missing: list[str]) -> dict:
        """누락된 레벨만 별도 호출하여 반환한다.

        Args:
            text: 원본 아티클 텍스트 (전처리 완료)
            missing: 누락된 레벨 이름 목록

        Returns:
            누락 레벨 데이터 dict (raw["senior"] 등)

        Raises:
            AIInternalError: 재시도 호출에서도 tool_use 블록이 없는 경우
        """
        retry_tool = build_retry_tool(missing)
        retry_prompt = build_retry_prompt(text, missing)

        try:
            response = self._client.converse(
                modelId=self._model,
                system=[
                    {"text": SYSTEM_PROMPT_ALL_LEVELS},
                    {"cachePoint": {"type": "default"}},
                ],
                messages=[{"role": "user", "content": [{"text": retry_prompt}]}],
                toolConfig=to_tool_config(retry_tool, _TOOL_NAME),
                inferenceConfig={"maxTokens": 4096, "temperature": 0.0},
            )
        except ReadTimeoutError as exc:
            raise AITimeoutError() from exc
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            raise AIUpstreamError(f"LLM API 오류 (retry): {code}") from exc
        except EndpointConnectionError as exc:
            raise AIUpstreamError("LLM 연결 실패 (retry)") from exc

        content = response["output"]["message"]["content"]
        tool_use_block = next((b for b in content if "toolUse" in b), None)
        if not tool_use_block:
            raise AIInternalError("레벨 재시도: LLM 응답에 tool_use 블록이 없습니다")

        return tool_use_block["toolUse"]["input"]
