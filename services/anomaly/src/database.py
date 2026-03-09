"""Database initialization for the anomaly detection service."""
import os

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings

DDL = """
CREATE SCHEMA IF NOT EXISTS anomaly;

CREATE TABLE IF NOT EXISTS anomaly.models (
    id SERIAL PRIMARY KEY,
    zone TEXT NOT NULL,
    arch TEXT NOT NULL,
    version TIMESTAMPTZ NOT NULL,
    val_loss REAL,
    epochs INTEGER,
    norm_stats JSONB DEFAULT '{}',
    model_path TEXT NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_anomaly_models_zone_active
    ON anomaly.models (zone, is_active);

CREATE TABLE IF NOT EXISTS anomaly.detections (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT now(),
    zone TEXT NOT NULL,
    channel TEXT NOT NULL,
    score REAL NOT NULL,
    predicted REAL,
    actual REAL,
    severity TEXT NOT NULL,
    source TEXT DEFAULT 'batch',
    model_id INTEGER REFERENCES anomaly.models(id)
);

CREATE INDEX IF NOT EXISTS idx_anomaly_detections_ts
    ON anomaly.detections USING BRIN (timestamp);

CREATE INDEX IF NOT EXISTS idx_anomaly_detections_zone
    ON anomaly.detections (zone, channel);
"""

engine = create_async_engine(settings.DATABASE_URL, pool_size=5, max_overflow=5)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create anomaly schema and tables."""
    async with engine.begin() as conn:
        for statement in DDL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(text(stmt))
    logger.info("Anomaly database schema initialized")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
