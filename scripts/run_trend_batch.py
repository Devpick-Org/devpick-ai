"""트렌드 분석 1회 실행 CLI (DP-386).

Usage:
    python scripts/run_trend_batch.py --unit weekly
    python scripts/run_trend_batch.py --unit daily --period-start 2026-04-21
    python scripts/run_trend_batch.py --unit monthly --force
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

from app.services.trend.orchestrator import TrendOrchestrator, compute_period

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _next_month_first(d: date) -> date:
    year = d.year + (d.month // 12)
    month = (d.month % 12) + 1
    return date(year, month, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="트렌드 분석 1회 실행")
    parser.add_argument(
        "--unit",
        required=True,
        choices=["daily", "weekly", "monthly"],
        help="트렌드 단위",
    )
    parser.add_argument(
        "--period-start",
        type=date.fromisoformat,
        default=None,
        dest="period_start",
        help="기간 시작 YYYY-MM-DD (미입력 시 자동 계산)",
    )
    parser.add_argument(
        "--period-end",
        type=date.fromisoformat,
        default=None,
        dest="period_end",
        help="기간 종료 YYYY-MM-DD (미입력 시 period-start + 단위 길이)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 스냅샷이 있어도 재생성",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL 환경변수를 설정하세요.")
        sys.exit(1)

    if args.period_start:
        period_start = args.period_start
        if args.period_end:
            period_end = args.period_end
        elif args.unit == "daily":
            period_end = period_start + timedelta(days=1)
        elif args.unit == "weekly":
            period_end = period_start + timedelta(weeks=1)
        else:
            period_end = _next_month_first(period_start)
    else:
        period_start, period_end = compute_period(args.unit)

    aws_region = os.environ.get("AWS_REGION", "ap-northeast-2")
    backend_url = os.environ.get("BACKEND_URL")
    internal_key = os.environ.get("INTERNAL_API_KEY")
    logger.info(
        "트렌드 배치 시작: unit=%s period=%s~%s force=%s cache_evict=%s",
        args.unit,
        period_start,
        period_end,
        args.force,
        bool(backend_url and internal_key),
    )

    orchestrator = TrendOrchestrator(
        database_url=database_url,
        aws_region=aws_region,
        backend_url=backend_url,
        internal_key=internal_key,
    )
    result = orchestrator.run(
        unit=args.unit,
        period_start=period_start,
        period_end=period_end,
        force=args.force,
    )

    print(
        f"완료: {result.date_label} | top_posts={len(result.top_posts)}"
        f" | top_posts_summary={'있음' if result.top_posts_summary else '없음'}"
        f" | collection_summary={'있음' if result.collection_summary else '없음'}"
    )


if __name__ == "__main__":
    main()
