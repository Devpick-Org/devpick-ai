"""AI 1차 답변 서비스 — Bedrock Converse API + Tool Use (DP-234)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import boto3
import pydantic
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from app.core.bedrock import to_tool_config
from app.core.exceptions import (
    AIBadRequestError,
    AIInternalError,
    AITimeoutError,
    AIUpstreamError,
)
from app.core.prompts.answer import ANSWER_TOOL, SYSTEM_PROMPT, build_user_prompt
from app.schemas.answer import AnswerResponse

logger = logging.getLogger(__name__)

_TOOL_NAME = "save_answer"


class AnswerService:
    """기술 질문에 대한 AI 1차 답변을 생성하는 서비스."""

    def __init__(
        self,
        aws_region: str = "ap-northeast-2",
        model: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
    ) -> None:
        self._client = boto3.client("bedrock-runtime", region_name=aws_region)
        self._model = model

    def answer(
        self,
        refined_title: str,
        refined_content: str,
        original_title: str | None = None,
        original_content: str | None = None,
        suggested_tags: list[str] | None = None,
        article_chunks: list[str] | None = None,
        rag_chunks: list[str] | None = None,
    ) -> tuple[AnswerResponse, list[str]]:
        """기술 질문에 대한 AI 답변을 생성한다.

        Args:
            refined_title: 개선된 질문 제목 (RefineResponse.refined_title)
            refined_content: 개선된 질문 본문 (RefineResponse.refined_content)
            original_title: 원본 질문 제목 (optional)
            original_content: 원본 질문 본문 (optional)
            suggested_tags: Refine 추천 태그 (optional)
            article_chunks: 관련 아티클 청크 텍스트 리스트 (optional)
            rag_chunks: RAG 유사 문서 청크 리스트 (optional)

        Returns:
            (AnswerResponse, references) 튜플.
            AnswerResponse의 related_contents는 빈 리스트 — 라우터에서 채움.
            references는 LLM이 활용한 content_id 리스트 (related_contents 조회용).

        Raises:
            AIBadRequestError: 빈 refined_title/refined_content
            AITimeoutError: LLM 타임아웃
            AIUpstreamError: LLM 연결 실패 / API 에러 / Rate Limit
            AIInternalError: 파싱 실패 / tool_use 블록 없음
        """
        try:
            user_prompt = build_user_prompt(
                refined_title=refined_title,
                refined_content=refined_content,
                original_title=original_title,
                original_content=original_content,
                suggested_tags=suggested_tags,
                article_chunks=article_chunks,
                rag_chunks=rag_chunks,
            )
        except ValueError as exc:
            raise AIBadRequestError(str(exc)) from exc

        try:
            response = self._client.converse(
                modelId=self._model,
                system=[
                    {"text": SYSTEM_PROMPT},
                    {"cachePoint": {"type": "default"}},
                ],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                toolConfig=to_tool_config(ANSWER_TOOL, _TOOL_NAME),
                inferenceConfig={"maxTokens": 4096, "temperature": 0.0},
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

        content_blocks = response["output"]["message"]["content"]
        tool_use_block = next((b for b in content_blocks if "toolUse" in b), None)
        if not tool_use_block:
            logger.error(
                "LLM 응답에 toolUse 블록이 없습니다. content=%s", content_blocks
            )
            raise AIInternalError("LLM 응답에 tool_use 블록이 없습니다")

        # references는 related_contents 조회용 — AnswerResponse 필드가 아니므로 분리
        raw_input = dict(tool_use_block["toolUse"]["input"])
        references: list[str] = raw_input.pop("references", [])

        try:
            payload = {
                **raw_input,
                "related_contents": [],  # 라우터에서 채움
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            return AnswerResponse.model_validate(payload), references
        except pydantic.ValidationError as exc:
            logger.error("AnswerResponse 파싱 실패: %s", exc)
            raise AIInternalError("AI 응답 파싱에 실패했습니다") from exc
