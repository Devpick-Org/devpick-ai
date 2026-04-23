"""PostgreSQL trend_snapshots 저장 레이어 (DP-378)."""

from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.schemas.trend import TrendResponse

logger = logging.getLogger(__name__)


class TrendSnapshotRepository:
    """트렌드 분석 결과를 trend_snapshots 테이블에 저장/조회한다.

    DDL은 Backend(DP-395)가 생성. AI 서버는 INSERT/SELECT만 담당.
    payload 컬럼에 TrendResponse 전체 JSON을 직렬화해 저장한다.
    """

    def __init__(self, database_url: str, pool_size: int = 3) -> None:
        self._engine: Engine = create_engine(
            database_url,
            pool_size=pool_size,
            pool_pre_ping=True,
        )

    def upsert(
        self,
        unit: str,
        scope: str,
        period_start: date,
        period_end: date,
        payload: TrendResponse,
        generated_at: datetime,
        expires_at: datetime | None = None,
    ) -> None:
        """트렌드 스냅샷을 INSERT하고, 동일 (unit, scope, period_start) 존재 시 UPDATE한다."""
        payload_json = payload.model_dump_json()
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO trend_snapshots
                        (unit, scope, period_start, period_end, payload, generated_at, expires_at)
                    VALUES
                        (:unit, :scope, :period_start, :period_end,
                         CAST(:payload AS JSONB), :generated_at, :expires_at)
                    ON CONFLICT (unit, scope, period_start)
                    DO UPDATE SET
                        period_end   = EXCLUDED.period_end,
                        payload      = EXCLUDED.payload,
                        generated_at = EXCLUDED.generated_at,
                        expires_at   = EXCLUDED.expires_at
                """),
                {
                    "unit": unit,
                    "scope": scope,
                    "period_start": period_start,
                    "period_end": period_end,
                    "payload": payload_json,
                    "generated_at": generated_at,
                    "expires_at": expires_at,
                },
            )
        logger.debug(
            "trend_snapshots upsert 완료: unit=%s scope=%s period_start=%s",
            unit,
            scope,
            period_start,
        )

    def get_latest(self, unit: str, scope: str = "global") -> TrendResponse | None:
        """unit+scope 기준 가장 최근 period_start 스냅샷을 반환한다."""
        with self._engine.begin() as conn:
            row = conn.execute(
                text("""
                    SELECT payload FROM trend_snapshots
                    WHERE unit = :unit AND scope = :scope
                    ORDER BY period_start DESC
                    LIMIT 1
                """),
                {"unit": unit, "scope": scope},
            ).fetchone()
        if row is None:
            return None
        return TrendResponse.model_validate_json(row[0])

    def get_by_period(
        self, unit: str, scope: str, period_start: date
    ) -> TrendResponse | None:
        """특정 (unit, scope, period_start) 스냅샷 1건을 반환한다."""
        with self._engine.begin() as conn:
            row = conn.execute(
                text("""
                    SELECT payload FROM trend_snapshots
                    WHERE unit = :unit AND scope = :scope AND period_start = :period_start
                    LIMIT 1
                """),
                {"unit": unit, "scope": scope, "period_start": period_start},
            ).fetchone()
        if row is None:
            return None
        return TrendResponse.model_validate_json(row[0])

    def close(self) -> None:
        self._engine.dispose()
