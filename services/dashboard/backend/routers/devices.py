"""Device Position CRUD API — manage sensor/camera positions on the floor plan."""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import DevicePosition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


# ── Request / Response Models ──────────────────────────────────────


class DevicePositionOut(BaseModel):
    id: int
    device_id: str
    zone: str
    x: float
    y: float
    device_type: str
    channels: list[str]


class CreateDevicePositionIn(BaseModel):
    device_id: str
    zone: str
    x: float
    y: float
    device_type: str = "sensor"
    channels: list[str] = []


class UpdateDevicePositionIn(BaseModel):
    x: float
    y: float
    zone: str | None = None


def _to_out(row: DevicePosition) -> DevicePositionOut:
    try:
        channels = json.loads(row.channels) if row.channels else []
    except (json.JSONDecodeError, TypeError):
        channels = []
    return DevicePositionOut(
        id=row.id,
        device_id=row.device_id,
        zone=row.zone,
        x=row.x,
        y=row.y,
        device_type=row.device_type or "sensor",
        channels=channels,
    )


# ── Endpoints ──────────────────────────────────────────────────────


@router.get("/positions/", response_model=list[DevicePositionOut])
async def list_device_positions(db: AsyncSession = Depends(get_db)):
    """List all device positions."""
    result = await db.execute(select(DevicePosition))
    return [_to_out(row) for row in result.scalars().all()]


@router.post("/positions/", response_model=DevicePositionOut, status_code=201)
async def create_device_position(
    body: CreateDevicePositionIn,
    db: AsyncSession = Depends(get_db),
):
    """Place a new device on the floor plan."""
    # Check for duplicate
    existing = await db.execute(
        select(DevicePosition).where(DevicePosition.device_id == body.device_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Device '{body.device_id}' already placed")

    row = DevicePosition(
        device_id=body.device_id,
        zone=body.zone,
        x=body.x,
        y=body.y,
        device_type=body.device_type,
        channels=json.dumps(body.channels),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("Device placed: %s at (%s, %s) in zone %s", body.device_id, body.x, body.y, body.zone)
    return _to_out(row)


@router.put("/positions/{device_id}", response_model=DevicePositionOut)
async def update_device_position(
    device_id: str,
    body: UpdateDevicePositionIn,
    db: AsyncSession = Depends(get_db),
):
    """Update device position (after drag)."""
    result = await db.execute(
        select(DevicePosition).where(DevicePosition.device_id == device_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    row.x = body.x
    row.y = body.y
    if body.zone is not None:
        row.zone = body.zone
    await db.commit()
    await db.refresh(row)
    logger.info("Device moved: %s to (%s, %s)", device_id, body.x, body.y)
    return _to_out(row)


@router.delete("/positions/{device_id}", status_code=204)
async def delete_device_position(
    device_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove a device from the floor plan."""
    result = await db.execute(
        select(DevicePosition).where(DevicePosition.device_id == device_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    await db.execute(
        sa_delete(DevicePosition).where(DevicePosition.device_id == device_id)
    )
    await db.commit()
    logger.info("Device removed: %s", device_id)
