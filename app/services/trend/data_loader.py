"""트렌드 계산용 데이터 로더 (DP-379)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from app.repositories.content_repository import ContentRepository
from app.repositories.summary_repository import SummaryRepository

logger = logging.getLogger(__name__)


@dataclass
class TrendRawData:
    cur_contents: list[dict] = field(default_factory=list)
    cur_view_counts: dict[str, int] = field(default_factory=dict)
    prev_view_counts: dict[str, int] = field(default_factory=dict)
    prev_contents: list[dict] = field(default_factory=list)
    summary_meta: dict[str, dict] = field(default_factory=dict)


class TrendDataLoader:
    """트렌드 계산에 필요한 cur/prev 기간 데이터를 병렬로 로드한다."""

    def __init__(
        self,
        content_repo: ContentRepository,
        summary_repo: SummaryRepository,
    ) -> None:
        self._content_repo = content_repo
        self._summary_repo = summary_repo

    def load(self, start: datetime, end: datetime) -> TrendRawData:
        """cur 기간 + prev 기간(동일 길이) 데이터를 병렬 로드한다.

        Args:
            start: 현재 기간 시작 (KST 기준)
            end: 현재 기간 종료 (KST 기준, 미포함)

        Returns:
            TrendRawData — cur 콘텐츠/조회수, prev 조회수, DynamoDB 메타
        """
        delta = end - start
        prev_start = start - delta

        with ThreadPoolExecutor(max_workers=4) as executor:
            f_contents = executor.submit(
                self._content_repo.find_by_published_range, start, end
            )
            f_prev_contents = executor.submit(
                self._content_repo.find_by_published_range, prev_start, start
            )
            f_cur_views = executor.submit(
                self._content_repo.find_view_counts_by_period, start, end
            )
            f_prev_views = executor.submit(
                self._content_repo.find_view_counts_by_period, prev_start, start
            )

        cur_contents = f_contents.result()
        prev_contents = f_prev_contents.result()
        cur_view_counts = f_cur_views.result()
        prev_view_counts = f_prev_views.result()

        content_ids = [c["id"] for c in cur_contents]
        summary_meta = (
            self._summary_repo.find_meta_by_content_ids(content_ids)
            if content_ids
            else {}
        )

        logger.debug(
            "TrendDataLoader.load 완료: contents=%d prev_contents=%d"
            " cur_views=%d prev_views=%d meta=%d",
            len(cur_contents),
            len(prev_contents),
            len(cur_view_counts),
            len(prev_view_counts),
            len(summary_meta),
        )

        return TrendRawData(
            cur_contents=cur_contents,
            cur_view_counts=cur_view_counts,
            prev_view_counts=prev_view_counts,
            prev_contents=prev_contents,
            summary_meta=summary_meta,
        )
