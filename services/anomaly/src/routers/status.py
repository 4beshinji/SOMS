"""Health and model status endpoints."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

# Will be set by main.py after scheduler is initialized
_scheduler = None
_mqtt_client = None


def set_scheduler(scheduler):
    global _scheduler
    _scheduler = scheduler


def set_mqtt_client(mqtt_client):
    global _mqtt_client
    _mqtt_client = mqtt_client


@router.get("/health")
async def health():
    from database import engine
    checks = {}

    # PostgreSQL check
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    # MQTT check
    if _mqtt_client and hasattr(_mqtt_client, "_client"):
        checks["mqtt"] = "ok" if _mqtt_client._client.is_connected() else "error: disconnected"
    else:
        checks["mqtt"] = "error: not initialized"

    all_ok = all(v == "ok" for v in checks.values())
    models = _scheduler.get_models() if _scheduler else {}
    status_code = 200 if all_ok else 503
    return JSONResponse(
        content={
            "status": "healthy" if all_ok else "degraded",
            "service": "anomaly",
            "checks": checks,
            "models_loaded": len(models),
        },
        status_code=status_code,
    )


@router.get("/models")
async def list_models():
    if not _scheduler:
        return {"models": {}}
    return {"models": _scheduler.get_models()}
