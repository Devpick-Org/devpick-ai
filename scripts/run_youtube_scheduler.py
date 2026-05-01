"""YouTube 수집 자동 실행 스케줄러 (DP-416).

매일 02:00 KST에 YouTube 영상을 수집한다.
트렌드 배치(00:05~00:15)와 시각을 분리해 DB 부하를 분산한다.

Usage:
    DATABASE_URL=postgresql://... YOUTUBE_API_KEY=... python scripts/run_youtube_scheduler.py
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

from scripts.run_youtube_batch import main as youtube_main

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

scheduler = BlockingScheduler(timezone="Asia/Seoul")
scheduler.add_job(youtube_main, "cron", hour=2, minute=0)

if __name__ == "__main__":
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL 환경변수를 설정하세요.", file=sys.stderr)
        sys.exit(1)
    print(
        "YouTube scheduler started.\n"
        "  수집: 매일 02:00 KST\n"
        "Press Ctrl+C to stop."
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("YouTube scheduler stopped.")
