"""트렌드 분석 자동 실행 스케줄러 (DP-386).

일/주/월 단위 트렌드를 KST 기준 자정 직후에 생성한다.
APScheduler BlockingScheduler — docker/서버 환경에서 장기 실행.

Usage:
    DATABASE_URL=postgresql://... python scripts/run_trend_scheduler.py
    Ctrl+C 로 중단
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

from apscheduler.schedulers.blocking import BlockingScheduler

from app.services.trend.orchestrator import TrendOrchestrator, compute_period

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")


def _run(unit: str) -> None:
    if not _DATABASE_URL:
        logger.error("DATABASE_URL 환경변수 필요")
        return
    try:
        orchestrator = TrendOrchestrator(
            database_url=_DATABASE_URL, aws_region=_AWS_REGION
        )
        period_start, period_end = compute_period(unit)
        orchestrator.run(unit, period_start, period_end)
    except Exception as exc:
        logger.error("%s 트렌드 배치 실패: %s", unit, exc, exc_info=True)


def run_daily() -> None:
    _run("daily")


def run_weekly() -> None:
    _run("weekly")


def run_monthly() -> None:
    _run("monthly")


scheduler = BlockingScheduler(timezone="Asia/Seoul")
# 매일 00:05 KST — 자정 조회수 집계 안정 후 실행
scheduler.add_job(run_daily, "cron", hour=0, minute=5)
# 매주 월요일 00:10 KST — 직전 한 주(월~월) 분석
scheduler.add_job(run_weekly, "cron", day_of_week="mon", hour=0, minute=10)
# 매월 1일 00:15 KST — 직전 월 분석
scheduler.add_job(run_monthly, "cron", day=1, hour=0, minute=15)

if __name__ == "__main__":
    if not _DATABASE_URL:
        print("DATABASE_URL 환경변수를 설정하세요.", file=sys.stderr)
        sys.exit(1)
    print(
        "Trend scheduler started.\n"
        "  daily:   매일 00:05 KST\n"
        "  weekly:  매주 월요일 00:10 KST\n"
        "  monthly: 매월 1일 00:15 KST\n"
        "Press Ctrl+C to stop."
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Trend scheduler stopped.")
