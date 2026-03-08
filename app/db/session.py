"""SQLAlchemy session and engine helpers."""

from __future__ import annotations

import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def get_connection_summary() -> dict[str, str]:
    """Return non-sensitive DB connection summary for logging/debug output."""
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        parsed = make_url(explicit_url)
        return {
            "host": parsed.host or "localhost",
            "port": str(parsed.port or 5432),
            "database": parsed.database or "devpick",
            "user": parsed.username or "devpick",
            "mode": "DATABASE_URL",
        }

    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "database": os.getenv("POSTGRES_DB", "devpick"),
        "user": os.getenv("POSTGRES_USER", "devpick"),
        "mode": "POSTGRES_FIELDS",
    }


def get_database_url() -> str:
    """Resolve database URL from env vars."""
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "devpick")
    user = os.getenv("POSTGRES_USER", "devpick")
    raw_password = os.getenv("POSTGRES_PASSWORD", "")
    if raw_password == "":
        raise ValueError(
            "Missing DB credentials: set DATABASE_URL first (recommended), "
            "or set POSTGRES_HOST/POSTGRES_PORT/POSTGRES_DB/POSTGRES_USER/POSTGRES_PASSWORD in .env."
        )

    password = quote_plus(raw_password)
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


def get_engine(database_url: str | None = None) -> Engine:
    """Create SQLAlchemy engine."""
    return create_engine(
        database_url or get_database_url(), future=True, pool_pre_ping=True
    )


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """Create SQLAlchemy session factory."""
    engine = get_engine(database_url=database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
