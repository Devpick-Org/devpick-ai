"""ContentRepository 단위 테스트 — SQLAlchemy mock 기반, 실제 DB 호출 없음."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.repositories.content_repository import ContentRepository
from app.schemas.normalized_content import NormalizedContent


def _make_item(
    source_name: str = "Kakao_Tech",
    title: str = "테스트 글",
    canonical_url: str = "https://example.com/post/1",
    body_candidate: str = "<p>본문</p>",
    published_at: str = "2026-03-01T00:00:00+00:00",
    thumbnail_url: str | None = "https://example.com/thumb.jpg",
    likes: int | None = None,
    score: int | None = None,
    view_count: int | None = None,
) -> NormalizedContent:
    return NormalizedContent(
        source_name=source_name,
        title=title,
        canonical_url=canonical_url,
        body_candidate=body_candidate,
        published_at=published_at,
        thumbnail_url=thumbnail_url,
        likes=likes,
        score=score,
        view_count=view_count,
    )


def _make_repo() -> tuple[ContentRepository, MagicMock]:
    """ContentRepository + mock engine을 반환한다."""
    with patch("app.repositories.content_repository.create_engine") as mock_engine_fn:
        mock_engine = MagicMock()
        mock_engine_fn.return_value = mock_engine
        repo = ContentRepository(database_url="postgresql://test/db")
    repo._engine = mock_engine
    return repo, mock_engine


def _setup_conn(mock_engine: MagicMock, source_id: str = "src-uuid-1") -> MagicMock:
    """engine.begin() context manager와 conn.execute() 반환값을 설정한다."""
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    # SELECT source → 존재하는 source 반환
    source_row = MagicMock()
    source_row.__getitem__ = lambda self, i: source_id

    # INSERT contents RETURNING id → 신규 저장됨
    content_row = MagicMock()
    content_row.__getitem__ = lambda self, i: "content-uuid-1"

    mock_conn.execute.return_value.fetchone.side_effect = [source_row, content_row]
    return mock_conn


# ── 빈 입력 ──────────────────────────────────────────────────────────────────


def test_save_contents_empty_list_returns_zero() -> None:
    repo, _ = _make_repo()
    result = repo.save_contents([])
    assert result.saved == 0
    assert result.skipped == 0
    assert result.inserted == []


# ── 정상 저장 ─────────────────────────────────────────────────────────────────


def test_save_contents_returns_saved_count() -> None:
    repo, mock_engine = _make_repo()
    _setup_conn(mock_engine)

    result = repo.save_contents([_make_item()])

    assert result.saved == 1
    assert result.skipped == 0
    assert len(result.inserted) == 1


def test_save_contents_inserted_contains_content_id_and_item() -> None:
    repo, mock_engine = _make_repo()
    item = _make_item()
    _setup_conn(mock_engine)

    result = repo.save_contents([item])

    content_id, saved_item = result.inserted[0]
    assert isinstance(content_id, str)
    assert saved_item is item


# ── ON CONFLICT (중복) ────────────────────────────────────────────────────────


def test_save_contents_conflict_counted_as_skipped() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    # source 조회 성공
    source_row = MagicMock()
    source_row.__getitem__ = lambda self, i: "src-uuid-1"
    # INSERT RETURNING → None (ON CONFLICT hit)
    mock_conn.execute.return_value.fetchone.side_effect = [source_row, None]

    result = repo.save_contents([_make_item()])

    assert result.saved == 0
    assert result.skipped == 1
    assert result.inserted == []


# ── canonical_url 없는 항목 ───────────────────────────────────────────────────


def test_save_contents_skips_item_without_canonical_url() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    item = _make_item(canonical_url=None)
    result = repo.save_contents([item])

    assert result.saved == 0
    assert result.skipped == 1
    mock_conn.execute.assert_not_called()


# ── 필드 매핑 ─────────────────────────────────────────────────────────────────


def test_save_contents_maps_body_candidate_to_original_content() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = _setup_conn(mock_engine)

    item = _make_item(body_candidate="<p>원본 HTML</p>")
    repo.save_contents([item])

    # INSERT 호출 시 params에 original_content가 body_candidate 값으로 들어가는지 확인
    insert_call = mock_conn.execute.call_args_list[-1]
    params = insert_call.args[1] if len(insert_call.args) > 1 else insert_call.kwargs
    assert params["original_content"] == "<p>원본 HTML</p>"


def test_save_contents_maps_score_field_to_db_score() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = _setup_conn(mock_engine)

    item = _make_item(score=42)
    repo.save_contents([item])

    insert_call = mock_conn.execute.call_args_list[-1]
    params = insert_call.args[1] if len(insert_call.args) > 1 else insert_call.kwargs
    assert params["score"] == 42


def test_save_contents_is_available_defaults_to_true() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = _setup_conn(mock_engine)

    repo.save_contents([_make_item()])

    insert_call = mock_conn.execute.call_args_list[-1]
    params = insert_call.args[1] if len(insert_call.args) > 1 else insert_call.kwargs
    assert params["is_available"] is True


def test_save_contents_invalid_published_at_becomes_none() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = _setup_conn(mock_engine)

    item = _make_item(published_at="not-a-date")
    repo.save_contents([item])

    insert_call = mock_conn.execute.call_args_list[-1]
    params = insert_call.args[1] if len(insert_call.args) > 1 else insert_call.kwargs
    assert params["published_at"] is None


# ── source 캐시 ───────────────────────────────────────────────────────────────


def test_source_cache_avoids_duplicate_select() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    source_row = MagicMock()
    source_row.__getitem__ = lambda self, i: "src-uuid-1"
    content_row1 = MagicMock()
    content_row1.__getitem__ = lambda self, i: "content-uuid-1"
    content_row2 = MagicMock()
    content_row2.__getitem__ = lambda self, i: "content-uuid-2"

    mock_conn.execute.return_value.fetchone.side_effect = [
        source_row,  # 첫 번째 항목: source SELECT
        content_row1,  # 첫 번째 항목: INSERT RETURNING
        content_row2,  # 두 번째 항목: INSERT RETURNING (source SELECT 스킵됨)
    ]

    item1 = _make_item(canonical_url="https://example.com/1")
    item2 = _make_item(canonical_url="https://example.com/2")
    result = repo.save_contents([item1, item2])

    # source SELECT 1번 + content INSERT 2번 = 3번 (캐시 적중 시 source SELECT 재호출 없음)
    assert result.saved == 2
    assert mock_conn.execute.call_count == 3


# ── source 자동 생성 ──────────────────────────────────────────────────────────


# ── find_by_published_range ───────────────────────────────────────────────────


def test_find_by_published_range_returns_rows() -> None:
    from datetime import datetime, timezone

    repo, mock_engine = _make_repo()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    mock_conn.execute.return_value.mappings.return_value.fetchall.return_value = [
        {
            "id": "cid-1",
            "title": "테스트 글",
            "translated_title": None,
            "category": "Backend",
            "tags": '["Python"]',
            "source_id": "src-1",
            "published_at": datetime(2026, 4, 14, tzinfo=timezone.utc),
        }
    ]

    result = repo.find_by_published_range(
        datetime(2026, 4, 14, tzinfo=timezone.utc),
        datetime(2026, 4, 21, tzinfo=timezone.utc),
    )

    assert len(result) == 1
    assert result[0]["id"] == "cid-1"
    assert result[0]["category"] == "Backend"


def test_find_by_published_range_empty_returns_empty_list() -> None:
    from datetime import datetime, timezone

    repo, mock_engine = _make_repo()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    mock_conn.execute.return_value.mappings.return_value.fetchall.return_value = []

    result = repo.find_by_published_range(
        datetime(2026, 4, 14, tzinfo=timezone.utc),
        datetime(2026, 4, 21, tzinfo=timezone.utc),
    )

    assert result == []


# ── find_view_counts_by_period ────────────────────────────────────────────────


def test_find_view_counts_by_period_returns_dict() -> None:
    from datetime import datetime, timezone

    repo, mock_engine = _make_repo()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    mock_conn.execute.return_value.fetchall.return_value = [
        ("cid-1", 10),
        ("cid-2", 3),
    ]

    result = repo.find_view_counts_by_period(
        datetime(2026, 4, 14, tzinfo=timezone.utc),
        datetime(2026, 4, 21, tzinfo=timezone.utc),
    )

    assert result == {"cid-1": 10, "cid-2": 3}


def test_find_view_counts_by_period_empty_returns_empty_dict() -> None:
    from datetime import datetime, timezone

    repo, mock_engine = _make_repo()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    mock_conn.execute.return_value.fetchall.return_value = []

    result = repo.find_view_counts_by_period(
        datetime(2026, 4, 14, tzinfo=timezone.utc),
        datetime(2026, 4, 21, tzinfo=timezone.utc),
    )

    assert result == {}


# ── find_by_ids ───────────────────────────────────────────────────────────────


def test_find_by_ids_returns_rows() -> None:
    from datetime import datetime, timezone

    repo, mock_engine = _make_repo()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    mock_conn.execute.return_value.mappings.return_value.fetchall.return_value = [
        {
            "id": "cid-1",
            "title": "글1",
            "translated_title": None,
            "category": "Backend",
            "tags": '["python"]',
            "source_id": "src-1",
            "published_at": datetime(2026, 4, 14, tzinfo=timezone.utc),
        }
    ]

    result = repo.find_by_ids(["cid-1"])

    assert len(result) == 1
    assert result[0]["id"] == "cid-1"
    assert result[0]["category"] == "Backend"
    call_params = mock_conn.execute.call_args.args[1]
    assert call_params["ids"] == ["cid-1"]


def test_find_by_ids_empty_returns_empty_list() -> None:
    repo, _ = _make_repo()
    assert repo.find_by_ids([]) == []


# ── source 자동 생성 ──────────────────────────────────────────────────────────


def test_get_or_create_source_inserts_when_not_found() -> None:
    repo, mock_engine = _make_repo()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    new_source_row = MagicMock()
    new_source_row.__getitem__ = lambda self, i: "new-src-uuid"
    content_row = MagicMock()
    content_row.__getitem__ = lambda self, i: "content-uuid-1"

    mock_conn.execute.return_value.fetchone.side_effect = [
        None,  # 첫 SELECT → 없음
        new_source_row,  # INSERT 후 재조회
        content_row,  # contents INSERT RETURNING
    ]

    result = repo.save_contents([_make_item()])

    # source SELECT(None) + INSERT source + re-SELECT + content INSERT = 4번
    assert mock_conn.execute.call_count == 4
    assert result.saved == 1
