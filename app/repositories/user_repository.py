"""PostgreSQL user_tags / tags / content_tags 조회 레이어."""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class UserRepository:
    """인사이트 생성에 필요한 유저·콘텐츠 데이터를 PostgreSQL에서 조회한다."""

    def __init__(self, database_url: str) -> None:
        self._engine: Engine = create_engine(
            database_url,
            pool_size=3,
            pool_pre_ping=True,
        )

    def find_keywords_by_user_id(self, user_id: str) -> list[str]:
        """user_tags JOIN tags 로 유저 설정 관심 키워드 이름 목록을 반환한다."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT t.name
                    FROM user_tags ut
                    JOIN tags t ON ut.tag_id = t.id
                    WHERE ut.user_id = :user_id
                    ORDER BY t.name
                """
                ),
                {"user_id": user_id},
            ).fetchall()
        return [row[0] for row in rows]

    def find_contents_by_tag_names(
        self, tag_names: list[str], limit: int = 3
    ) -> list[dict]:
        """미탐색 태그 이름 기반으로 추천 콘텐츠 제목 목록을 반환한다.

        Returns:
            [{"title": str}, ...]
        """
        if not tag_names:
            return []

        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT c.title
                    FROM contents c
                    JOIN content_tags ct ON c.id = ct.content_id
                    JOIN tags t ON ct.tag_id = t.id
                    WHERE t.name = ANY(:tag_names)
                      AND c.is_available = true
                    GROUP BY c.id, c.title, c.published_at
                    ORDER BY c.published_at DESC
                    LIMIT :limit
                """
                ),
                {"tag_names": tag_names, "limit": limit},
            ).fetchall()
        return [{"title": row[0]} for row in rows]

    def close(self) -> None:
        self._engine.dispose()
