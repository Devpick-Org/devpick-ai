"""트렌드 분석 배치 오케스트레이터 (DP-386)."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone

from app.core.exceptions import AITimeoutError, AIUpstreamError
from app.repositories.content_repository import ContentRepository
from app.repositories.summary_repository import SummaryRepository
from app.repositories.trend_repository import TrendSnapshotRepository
from app.schemas.trend import TopContent, TrendResponse
from app.services.trend.collection_summary import (
    CollectionSummaryGenerator,
    TrendSignals,
)
from app.services.trend.data_loader import TrendDataLoader
from app.services.trend.frequency import FrequencyAnalyzer
from app.services.trend.normalize import TagNormalizer
from app.services.trend.ranking import TrendRanker
from app.services.trend.tfidf import TfidfAnalyzer
from app.services.trend.tokenizer import KoreanTokenizer
from app.services.trend.top_posts_summary import TopPostsSummaryGenerator

logger = logging.getLogger(__name__)


def compute_period(unit: str, reference_date: date | None = None) -> tuple[date, date]:
    """unit 기준 직전 기간의 (period_start, period_end) 를 반환한다.

    daily  → 어제 자정 ~ 오늘 자정
    weekly → 지난 주 월요일 ~ 이번 주 월요일 (월요일 실행 기준)
    monthly → 지난달 1일 ~ 이번달 1일
    """
    today = reference_date or date.today()
    if unit == "daily":
        return today - timedelta(days=1), today
    if unit == "weekly":
        monday = today - timedelta(days=today.weekday())
        return monday - timedelta(weeks=1), monday
    if unit == "monthly":
        first = today.replace(day=1)
        prev_first = (first - timedelta(days=1)).replace(day=1)
        return prev_first, first
    raise ValueError(f"지원하지 않는 unit: {unit!r}")


def _extract_tags(contents: list[dict]) -> list[str]:
    tags: list[str] = []
    for c in contents:
        raw = c.get("tags") or []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                raw = []
        tags.extend(raw)
    return tags


def _make_date_label(unit: str, period_start: date, period_end: date) -> str:
    if unit == "daily":
        return f"{period_start.month}월 {period_start.day}일"
    if unit == "weekly":
        return f"{period_start.month}월 {period_start.day}일 주간"
    if unit == "monthly":
        return f"{period_start.year}년 {period_start.month}월"
    return str(period_start)


def _to_top_content(
    content: dict,
    view_count: int | None,
    prev_view_counts: dict[str, int],
) -> TopContent:
    tags = content.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, ValueError):
            tags = []

    prev_vc = prev_view_counts.get(content["id"], 0)
    cur_vc = view_count or 0
    change_rate = round((cur_vc - prev_vc) / prev_vc * 100, 1) if prev_vc > 0 else None

    return TopContent(
        id=content["id"],
        title=content.get("title", ""),
        translated_title=content.get("translated_title"),
        source_name=content.get("source_name") or "unknown",
        tags=tags,
        view_count=view_count,
        thumbnail_url=content.get("thumbnail_url"),
        category=content.get("category"),
        change_rate=change_rate,
    )


class TrendOrchestrator:
    """일/주/월 단위 트렌드 분석 배치 오케스트레이터.

    TagNormalizer → FrequencyAnalyzer → TfidfAnalyzer → TrendRanker →
    TopPostsSummaryGenerator + CollectionSummaryGenerator →
    TrendSnapshotRepository.upsert()
    """

    def __init__(
        self,
        database_url: str,
        aws_region: str = "ap-northeast-2",
        model: str = "global.anthropic.claude-sonnet-4-6",
    ) -> None:
        content_repo = ContentRepository(database_url)
        summary_repo = SummaryRepository(aws_region=aws_region)
        self._loader = TrendDataLoader(content_repo, summary_repo)
        self._normalizer = TagNormalizer()
        self._freq = FrequencyAnalyzer()
        self._tokenizer = KoreanTokenizer()
        self._tfidf = TfidfAnalyzer()
        self._ranker = TrendRanker()
        self._top_posts_gen = TopPostsSummaryGenerator(
            aws_region=aws_region,
            model=model,
            summary_repo=summary_repo,
        )
        self._collection_gen = CollectionSummaryGenerator(
            aws_region=aws_region,
            model=model,
        )
        self._snapshot_repo = TrendSnapshotRepository(database_url)

    def run(
        self,
        unit: str,
        period_start: date,
        period_end: date,
        force: bool = False,
    ) -> TrendResponse:
        """트렌드 분석을 실행하고 스냅샷을 저장한 뒤 TrendResponse를 반환한다.

        force=False 이고 동일 (unit, period_start) 스냅샷이 이미 존재하면 즉시 반환한다.
        """
        if not force:
            existing = self._snapshot_repo.get_by_period(unit, "global", period_start)
            if existing is not None:
                logger.info(
                    "이미 존재하는 스냅샷 — skip: unit=%s period_start=%s",
                    unit,
                    period_start,
                )
                return existing

        start = datetime.combine(period_start, time.min)
        end = datetime.combine(period_end, time.min)

        raw = self._loader.load(start, end)

        # 태그 정규화 + 빈도 집계
        cur_tags = self._normalizer.normalize(_extract_tags(raw.cur_contents))
        prev_tags = self._normalizer.normalize(_extract_tags(raw.prev_contents))
        tag_frequencies = self._freq.analyze(cur_tags, prev_tags)

        # TF-IDF 키워드 (제목 기반, 이름만 추출)
        titles = [c.get("title", "") for c in raw.cur_contents]
        tokenized = self._tokenizer.tokenize(titles)
        tfidf_keywords = [kw for kw, _ in self._tfidf.extract(tokenized)[:15]]

        # Top 5 콘텐츠 랭킹
        top_contents_raw = self._ranker.rank_contents(
            raw.cur_view_counts, raw.cur_contents
        )
        top_posts = [
            _to_top_content(c, raw.cur_view_counts.get(c["id"]), raw.prev_view_counts)
            for c in top_contents_raw
        ]

        # 이전 기간 스냅샷 조회 (LLM 비교 서술용)
        delta = end - start
        prev_period_start = (start - delta).date()
        prev_snapshot = self._snapshot_repo.get_by_period(
            unit, "global", prev_period_start
        )
        prev_top_posts_summary = (
            prev_snapshot.top_posts_summary if prev_snapshot else None
        )
        prev_collection_summary = (
            prev_snapshot.collection_summary if prev_snapshot else None
        )

        # Top posts 서사 요약 — 실패 시 None (스냅샷 저장 계속)
        top_posts_summary: str | None = None
        try:
            top_posts_summary = self._top_posts_gen.generate(
                top_contents_raw,
                unit,
                str(period_start),
                str(period_end),
                prev_top_posts_summary,
            )
        except (AIUpstreamError, AITimeoutError) as exc:
            logger.warning("top_posts_summary 생성 실패 — skip: %s", exc)
        except Exception as exc:
            logger.warning("top_posts_summary 예외 — skip: %s", exc)

        # 수집 동향 서사 요약 — 내부에서 None 반환 (daily 포함)
        signals = TrendSignals(
            unit=unit,
            period_start=str(period_start),
            period_end=str(period_end),
            cur_content_count=len(raw.cur_contents),
            prev_content_count=len(raw.prev_contents),
            top_tags=tag_frequencies,
            tfidf_keywords=tfidf_keywords,
            prev_summary=prev_collection_summary,
        )
        collection_summary = self._collection_gen.generate(signals)

        date_label = _make_date_label(unit, period_start, period_end)
        response = TrendResponse(
            unit=unit,
            period_start=period_start,
            period_end=period_end,
            date_label=date_label,
            top_posts=top_posts,
            top_posts_summary=top_posts_summary,
            collection_summary=collection_summary,
        )

        self._snapshot_repo.upsert(
            unit=unit,
            scope="global",
            period_start=period_start,
            period_end=period_end,
            payload=response,
            generated_at=datetime.now(tz=timezone.utc),
        )

        logger.info(
            "트렌드 배치 완료: unit=%s period=%s~%s contents=%d top_posts=%d",
            unit,
            period_start,
            period_end,
            len(raw.cur_contents),
            len(top_posts),
        )
        return response
