"""APScheduler-based scheduler: runs collect_and_push every 6 hours."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apscheduler.schedulers.blocking import BlockingScheduler

from scripts.run_collect_and_push import main

scheduler = BlockingScheduler()
scheduler.add_job(main, "interval", hours=6, next_run_time=datetime.now())

if __name__ == "__main__":
    print(
        "Scheduler started. Running immediately, then every 6 hours. Press Ctrl+C to stop."
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")
