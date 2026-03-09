"""Health and model status endpoints."""
from fastapi import APIRouter

router = APIRouter()

# Will be set by main.py after scheduler is initialized
_scheduler = None


def set_scheduler(scheduler):
    global _scheduler
    _scheduler = scheduler


@router.get("/health")
async def health():
    models = _scheduler.get_models() if _scheduler else {}
    return {
        "status": "ok",
        "service": "soms-anomaly",
        "models_loaded": len(models),
    }


@router.get("/models")
async def list_models():
    if not _scheduler:
        return {"models": {}}
    return {"models": _scheduler.get_models()}
