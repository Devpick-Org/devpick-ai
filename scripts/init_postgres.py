"""PostgreSQL 초기화 — AI 서버 전용 UNIQUE 인덱스 생성.

배포 시 1회 실행한다. 멱등성 보장 (IF NOT EXISTS).

Usage::

    DATABASE_URL=postgresql://user:pass@host:5432/devpick python scripts/init_postgres.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print(
            "[init_postgres] ERROR: DATABASE_URL이 설정되지 않았습니다.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
            print("[init_postgres] PostgreSQL 연결 성공")

            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_contents_canonical_url
                    ON contents (canonical_url)
                """
                )
            )
            print("[init_postgres] idx_contents_canonical_url — OK")

            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_content_sources_name
                    ON content_sources (name)
                """
                )
            )
            print("[init_postgres] idx_content_sources_name — OK")

            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_contents_source_title
                    ON contents (source_id, lower(title))
                """
                )
            )
            print("[init_postgres] idx_contents_source_title — OK")

        print("[init_postgres] 초기화 완료")

    except Exception as error:
        print(f"[init_postgres] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
