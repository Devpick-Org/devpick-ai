"""Check PostgreSQL connectivity using current .env configuration."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import get_connection_summary, get_engine


def print_env_hint() -> None:
    print("[HINT] Set one of these in .env:")
    print(
        "- DATABASE_URL=postgresql://devpick:devpick_local_pg_2026@localhost:5432/devpick"
    )
    print(
        "- or leave DATABASE_URL empty and set POSTGRES_HOST/POSTGRES_PORT/POSTGRES_DB/POSTGRES_USER/POSTGRES_PASSWORD"
    )
    print("[EXAMPLE]")
    print("POSTGRES_HOST=localhost")
    print("POSTGRES_PORT=5432")
    print("POSTGRES_DB=devpick")
    print("POSTGRES_USER=devpick")
    print("POSTGRES_PASSWORD=devpick_local_pg_2026")


def print_missing_env_details() -> None:
    import os

    database_url = os.getenv("DATABASE_URL", "").strip()
    fields = {
        "POSTGRES_HOST": os.getenv("POSTGRES_HOST", "").strip(),
        "POSTGRES_PORT": os.getenv("POSTGRES_PORT", "").strip(),
        "POSTGRES_DB": os.getenv("POSTGRES_DB", "").strip(),
        "POSTGRES_USER": os.getenv("POSTGRES_USER", "").strip(),
        "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD", "").strip(),
    }
    missing = [name for name, value in fields.items() if not value]

    if database_url:
        print("[INFO] DATABASE_URL is set. POSTGRES_* values are ignored.")
        return

    if missing:
        print(f"[INFO] Missing env vars: {', '.join(missing)}")
    else:
        print("[INFO] DATABASE_URL is empty, using POSTGRES_* values.")


def main() -> None:
    summary = get_connection_summary()
    print(
        "[DB] "
        f"mode={summary['mode']} "
        f"host={summary['host']} "
        f"port={summary['port']} "
        f"database={summary['database']} "
        f"user={summary['user']}"
    )

    engine = get_engine()
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        value = result.scalar_one()

    print("[OK] PostgreSQL connection success")
    print(f"[OK] SELECT 1 성공 ({value})")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"[ERROR] PostgreSQL connection failed: {error}")
        print_missing_env_details()
        print_env_hint()
        raise
