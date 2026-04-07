"""APScheduler-based scheduler.

- 통합 수집 (백필 + incremental): 6시간마다
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apscheduler.schedulers.blocking import BlockingScheduler

from scripts.run_backfill_batch import main as collect_main

scheduler = BlockingScheduler()
scheduler.add_job(collect_main, "interval", hours=6, next_run_time=datetime.now())

if __name__ == "__main__":
    print(
        "Scheduler started.\n"
        "  통합 수집 (백필 + incremental): 즉시 실행 후 6시간마다\n"
        "Press Ctrl+C to stop."
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")
