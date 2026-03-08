"""Tests for source/content upsert persistence behavior."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Base, Content, ContentSource
from app.db.session import get_database_url
from app.repositories.content_repository import ContentRepository
from app.repositories.content_source_repository import ContentSourceRepository
from app.schemas.normalized_content import NormalizedContent
from app.schemas.source import SourceConfig
from app.services.persist_service import PersistService


def make_source() -> SourceConfig:
    return SourceConfig(
        name="NAVER_D2",
        feed_url="https://d2.naver.com/d2.atom",
        site_url="https://d2.naver.com",
        parser_type="atom",
        content_level=2,
        active=True,
        note="",
    )


def make_normalized(url: str, title: str = "title") -> NormalizedContent:
    return NormalizedContent(
        source_name="NAVER_D2",
        title=title,
        canonical_url=url,
        published_at="2026-03-08T12:00:00+00:00",
        preview="preview",
        body_candidate="body",
        body_source="content_raw",
        content_kind="full_body",
        entry_external_id="ext-1",
    )


def setup_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return Session(bind=engine)


def test_source_upsert() -> None:
    session = setup_session()
    repository = ContentSourceRepository()

    first = repository.upsert(
        session,
        name="NAVER_D2",
        url="https://d2.naver.com",
        collect_method="rss",
        is_active=True,
    )
    second = repository.upsert(
        session,
        name="NAVER_D2",
        url="https://d2.naver.com/new",
        collect_method="rss",
        is_active=False,
    )

    assert first.id == second.id
    assert second.url == "https://d2.naver.com/new"
    assert second.is_active is False


def test_content_upsert() -> None:
    session = setup_session()
    source = ContentSource(
        name="NAVER_D2",
        url="https://d2.naver.com",
        collect_method="rss",
        is_active=True,
    )
    session.add(source)
    session.flush()

    repository = ContentRepository()
    content = repository.upsert(
        session,
        source_id=source.id,
        normalized=make_normalized("https://example.com/a", "Title A"),
    )

    assert content.id is not None
    assert content.canonical_url == "https://example.com/a"
    assert content.original_content == "body"


def test_canonical_url_upsert_updates_existing_row() -> None:
    session = setup_session()
    service = PersistService()
    source = make_source()

    service.persist_normalized(
        session,
        source=source,
        normalized_items=[make_normalized("https://example.com/a", "Old Title")],
    )

    service.persist_normalized(
        session,
        source=source,
        normalized_items=[make_normalized("https://example.com/a", "New Title")],
    )

    rows = (
        session.execute(
            select(Content).where(Content.canonical_url == "https://example.com/a")
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].title == "New Title"


def test_database_url_takes_precedence(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/devpick")
    monkeypatch.setenv("POSTGRES_PASSWORD", "ignored")
    assert get_database_url() == "postgresql://u:p@localhost:5432/devpick"


def test_postgres_fields_fallback(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "devpick")
    monkeypatch.setenv("POSTGRES_USER", "devpick")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw")

    url = get_database_url()
    assert url.startswith("postgresql+psycopg2://devpick:pw@localhost:5432/devpick")


def test_missing_password_message(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "devpick")
    monkeypatch.setenv("POSTGRES_USER", "devpick")
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    try:
        get_database_url()
        assert False, "Expected ValueError when POSTGRES_PASSWORD is missing"
    except ValueError as error:
        assert "DATABASE_URL" in str(error)
        assert "POSTGRES_PASSWORD" in str(error)
