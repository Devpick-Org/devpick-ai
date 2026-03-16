"""Unit tests for SentIdStore."""

from __future__ import annotations

import pytest

from app.stores.sent_id_store import SentIdStore


@pytest.fixture
def store(tmp_path):
    return SentIdStore(base_dir=str(tmp_path / "sent_ids"))


def test_load_returns_empty_set_when_file_missing(store):
    result = store.load("some_source")
    assert result == set()


def test_add_saves_ids_and_load_returns_them(store):
    store.add("source_a", {"id1", "id2"})
    result = store.load("source_a")
    assert result == {"id1", "id2"}


def test_add_preserves_existing_ids(store):
    store.add("source_a", {"id1"})
    store.add("source_a", {"id2"})
    result = store.load("source_a")
    assert result == {"id1", "id2"}


def test_add_deduplicates_on_reinsert(store):
    store.add("source_a", {"id1", "id2"})
    store.add("source_a", {"id1"})
    result = store.load("source_a")
    assert result == {"id1", "id2"}
    # Confirm no duplicates in stored file
    path = store._path("source_a")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(set(lines))


def test_load_add_load_accumulates(store):
    store.add("feed_x", {"a", "b"})
    existing = store.load("feed_x")
    assert "a" in existing and "b" in existing

    store.add("feed_x", {"c"})
    final = store.load("feed_x")
    assert final == {"a", "b", "c"}


def test_different_sources_are_isolated(store):
    store.add("source_1", {"x"})
    store.add("source_2", {"y"})
    assert store.load("source_1") == {"x"}
    assert store.load("source_2") == {"y"}
