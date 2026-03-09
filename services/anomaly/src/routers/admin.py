"""Admin endpoints for training and anomaly queries."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from loguru import logger
from sqlalchemy import text

from database import engine
from model.trainer import Trainer

router = APIRouter(prefix="/admin")

_trainer = None


def set_trainer(trainer: Trainer):
    global _trainer
    _trainer = trainer


@router.post("/train")
async def trigger_training(zone: str | None = None):
    """Manually trigger model training."""
    if not _trainer:
        return {"error": "Trainer not initialized"}

    if zone:
        result = await _trainer.train_zone(zone)
        return {"results": [result] if result else []}
    else:
        results = await _trainer.train_all_zones()
        return {"results": results}


@router.get("/anomalies")
async def list_anomalies(
    zone: str | None = None,
    channel: str | None = None,
    severity: str | None = None,
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Query recent anomaly detections."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    conditions = ["timestamp >= :since"]
    params: dict = {"since": since, "limit": limit}

    if zone:
        conditions.append("zone = :zone")
        params["zone"] = zone
    if channel:
        conditions.append("channel = :channel")
        params["channel"] = channel
    if severity:
        conditions.append("severity = :severity")
        params["severity"] = severity

    where = " AND ".join(conditions)

    async with engine.begin() as conn:
        rows = await conn.execute(
            text(f"""
                SELECT id, timestamp, zone, channel, score, predicted, actual,
                       severity, source, model_id
                FROM anomaly.detections
                WHERE {where}
                ORDER BY timestamp DESC
                LIMIT :limit
            """),
            params,
        )

        detections = []
        for row in rows:
            detections.append({
                "id": row[0],
                "timestamp": row[1].isoformat() if row[1] else None,
                "zone": row[2],
                "channel": row[3],
                "score": row[4],
                "predicted": row[5],
                "actual": row[6],
                "severity": row[7],
                "source": row[8],
                "model_id": row[9],
            })

    return {"detections": detections, "count": len(detections)}
