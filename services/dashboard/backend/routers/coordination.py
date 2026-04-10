"""Cross-dashboard coordination API — trigger synchronized events across displays."""
import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from jwt_auth import AuthUser, require_service_auth, get_current_user
from models import DisplayPosition

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_USER = os.getenv("MQTT_USER", "soms")
MQTT_PASS = os.getenv("MQTT_PASS", "soms_dev_mqtt")
SOMS_ENV = os.environ.get("SOMS_ENV", "development")

router = APIRouter(prefix="/coordination", tags=["coordination"])


async def optional_auth(
    user: AuthUser | None = Depends(get_current_user),
) -> AuthUser:
    if user is not None:
        return user
    if SOMS_ENV == "development":
        return AuthUser(id=0, username="system", display_name="System")
    raise HTTPException(status_code=401, detail="Authentication required")


# ── Request / Response Models ──────────────────────────────────────


class AvatarTraversalRequest(BaseModel):
    display_ids: list[str] | None = None  # null = auto-detect all by sort_order
    animation: str = "run"
    speed: str = "normal"  # "slow", "normal", "fast"
    delay_between_ms: int = 1800  # overlap between adjacent displays


class SequenceEntry(BaseModel):
    display_id: str
    order: int
    enter_ms: int
    exit_ms: int
    enter_edge: str
    exit_edge: str


class AvatarTraversalResponse(BaseModel):
    event_id: str
    event_type: str = "avatar_traversal"
    animation: str
    sequence: list[SequenceEntry]
    start_at_epoch_ms: int


# ── Speed → duration mapping ──────────────────────────────────────

_SPEED_DURATION_MS = {
    "slow": 3000,
    "normal": 2000,
    "fast": 1200,
}


# ── Endpoints ──────────────────────────────────────────────────────


@router.post("/avatar-traversal", response_model=AvatarTraversalResponse)
async def trigger_avatar_traversal(
    body: AvatarTraversalRequest,
    db: AsyncSession = Depends(get_db),
    _auth: AuthUser = Depends(optional_auth),
):
    """Trigger an avatar traversal animation across multiple displays.

    Publishes a coordination event via MQTT with timing for each display.
    """
    # Resolve display list
    if body.display_ids:
        # Fetch in specified order
        result = await db.execute(
            select(DisplayPosition).where(
                DisplayPosition.display_id.in_(body.display_ids)
            )
        )
        rows = result.scalars().all()
        # Preserve requested order
        row_map = {r.display_id: r for r in rows}
        displays = [row_map[did] for did in body.display_ids if did in row_map]
    else:
        # Auto-detect all active displays by sort_order
        result = await db.execute(
            select(DisplayPosition)
            .where(DisplayPosition.is_active.is_(True))
            .order_by(DisplayPosition.sort_order)
        )
        displays = list(result.scalars().all())

    if len(displays) < 1:
        raise HTTPException(status_code=400, detail="No displays found for traversal")

    # Calculate timing sequence
    duration_ms = _SPEED_DURATION_MS.get(body.speed, 2000)
    delay = body.delay_between_ms
    sequence: list[SequenceEntry] = []

    for i, disp in enumerate(displays):
        enter_ms = i * delay
        exit_ms = enter_ms + duration_ms
        sequence.append(SequenceEntry(
            display_id=disp.display_id,
            order=i,
            enter_ms=enter_ms,
            exit_ms=exit_ms,
            enter_edge="left",
            exit_edge="right",
        ))

    event_id = str(uuid.uuid4())[:8]

    import time
    start_at = int(time.time() * 1000) + 500  # 500ms from now

    payload = AvatarTraversalResponse(
        event_id=event_id,
        animation=body.animation,
        sequence=sequence,
        start_at_epoch_ms=start_at,
    )

    # Publish to MQTT
    topic = f"soms/coordination/{event_id}/sequence"
    try:
        import paho.mqtt.publish as mqtt_publish
        mqtt_publish.single(
            topic,
            json.dumps(payload.model_dump()),
            hostname=MQTT_BROKER,
            auth={"username": MQTT_USER, "password": MQTT_PASS},
        )
        logger.info("Published avatar traversal to %s (%d displays)", topic, len(sequence))
    except Exception as e:
        logger.warning("MQTT publish failed for coordination %s: %s", event_id, e)

    return payload
