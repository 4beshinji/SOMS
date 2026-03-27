"""
Database setup for the events schema.

Uses raw SQL DDL (no Alembic) — Phase 0 simplicity.
Tables are created with IF NOT EXISTS for idempotent startup.
"""
import os
from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import text

_engine: AsyncEngine | None = None

DDL = """
CREATE SCHEMA IF NOT EXISTS events;

CREATE TABLE IF NOT EXISTS events.raw_events (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    zone        TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    source_device TEXT,
    data        JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_raw_events_ts
    ON events.raw_events USING BRIN (timestamp);

CREATE INDEX IF NOT EXISTS idx_raw_events_zone_type
    ON events.raw_events (zone, event_type);

CREATE TABLE IF NOT EXISTS events.llm_decisions (
    id                  BIGSERIAL PRIMARY KEY,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),
    cycle_duration_sec  REAL NOT NULL,
    iterations          INTEGER NOT NULL,
    total_tool_calls    INTEGER NOT NULL,
    trigger_events      JSONB NOT NULL DEFAULT '[]',
    tool_calls          JSONB NOT NULL DEFAULT '[]',
    world_state_snapshot JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_llm_decisions_ts
    ON events.llm_decisions USING BRIN (timestamp);

CREATE TABLE IF NOT EXISTS events.hourly_aggregates (
    hub_id       TEXT NOT NULL DEFAULT 'soms-brain',
    period_start TIMESTAMPTZ NOT NULL,
    zones        JSONB NOT NULL DEFAULT '{}',
    tasks_created INTEGER NOT NULL DEFAULT 0,
    llm_cycles   INTEGER NOT NULL DEFAULT 0,
    device_health JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (hub_id, period_start)
);

CREATE TABLE IF NOT EXISTS events.aggregation_state (
    id                    INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    last_aggregated_hour  TIMESTAMPTZ,
    last_run_at           TIMESTAMPTZ
);

INSERT INTO events.aggregation_state (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS events.spatial_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    zone        TEXT NOT NULL,
    camera_id   TEXT,
    data        JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_spatial_snapshots_ts
    ON events.spatial_snapshots USING BRIN (timestamp);

CREATE INDEX IF NOT EXISTS idx_spatial_snapshots_zone
    ON events.spatial_snapshots (zone);

CREATE TABLE IF NOT EXISTS events.spatial_heatmap_hourly (
    zone            TEXT NOT NULL,
    period_start    TIMESTAMPTZ NOT NULL,
    grid_cols       INTEGER NOT NULL,
    grid_rows       INTEGER NOT NULL,
    cell_counts     JSONB NOT NULL DEFAULT '[]',
    person_count_avg REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (zone, period_start)
);

ALTER TABLE events.raw_events ADD COLUMN IF NOT EXISTS region_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE events.llm_decisions ADD COLUMN IF NOT EXISTS region_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE events.hourly_aggregates ADD COLUMN IF NOT EXISTS region_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE events.spatial_snapshots ADD COLUMN IF NOT EXISTS region_id TEXT NOT NULL DEFAULT 'local';

CREATE TABLE IF NOT EXISTS events.tracking_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    person_count INTEGER NOT NULL DEFAULT 0,
    data        JSONB NOT NULL DEFAULT '{}',
    region_id   TEXT NOT NULL DEFAULT 'local'
);

CREATE INDEX IF NOT EXISTS idx_tracking_snapshots_ts
    ON events.tracking_snapshots USING BRIN (timestamp);

CREATE TABLE IF NOT EXISTS events.person_tracks (
    id          BIGSERIAL PRIMARY KEY,
    global_id   INTEGER NOT NULL,
    first_seen  TIMESTAMPTZ NOT NULL,
    last_seen   TIMESTAMPTZ NOT NULL,
    zone_transitions JSONB NOT NULL DEFAULT '[]',
    total_duration_sec REAL NOT NULL DEFAULT 0,
    region_id   TEXT NOT NULL DEFAULT 'local'
);

CREATE INDEX IF NOT EXISTS idx_person_tracks_global_id
    ON events.person_tracks (global_id);

CREATE TABLE IF NOT EXISTS events.reports (
    id                  BIGSERIAL PRIMARY KEY,
    report_type         TEXT NOT NULL,
    period_start        TIMESTAMPTZ NOT NULL,
    period_end          TIMESTAMPTZ NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_used          TEXT NOT NULL,
    generation_time_sec REAL NOT NULL,
    status              TEXT NOT NULL DEFAULT 'completed',
    content             JSONB NOT NULL DEFAULT '{}',
    raw_markdown        TEXT,
    summary             TEXT,
    region_id           TEXT NOT NULL DEFAULT 'local'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_type_period
    ON events.reports (report_type, period_start);

CREATE TABLE IF NOT EXISTS events.device_registry_snapshot (
    id          INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    snapshot    JSONB NOT NULL DEFAULT '[]',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def get_engine() -> AsyncEngine | None:
    return _engine


async def init_db() -> AsyncEngine | None:
    """Create engine and run DDL. Returns engine or None if DATABASE_URL is not set."""
    global _engine

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.warning("DATABASE_URL not set — event store disabled")
        return None

    _engine = create_async_engine(
        database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )

    async with _engine.begin() as conn:
        for statement in DDL.strip().split(";"):
            statement = statement.strip()
            if statement:
                await conn.execute(text(statement))

    logger.info("Event store schema initialized (events.*)")
    return _engine
