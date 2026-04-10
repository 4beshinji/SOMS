"""Display Position CRUD API — manage dashboard display positions on the floor plan."""
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from jwt_auth import AuthUser, get_current_user
from models import DisplayPosition
import schemas

SOMS_ENV = os.environ.get("SOMS_ENV", "development")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/displays", tags=["displays"])


async def optional_auth(
    user: AuthUser | None = Depends(get_current_user),
) -> AuthUser:
    """In development mode, allow unauthenticated access."""
    if user is not None:
        return user
    if SOMS_ENV == "development":
        return AuthUser(id=0, username="editor", display_name="Zone Editor")
    raise HTTPException(status_code=401, detail="Authentication required")


# ── Endpoints ──────────────────────────────────────────────────────


@router.get("/", response_model=list[schemas.DisplayOut])
async def list_displays(db: AsyncSession = Depends(get_db)):
    """List all registered displays."""
    result = await db.execute(
        select(DisplayPosition).order_by(DisplayPosition.sort_order)
    )
    return result.scalars().all()


@router.get("/{display_id}", response_model=schemas.DisplayOut)
async def get_display(display_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single display by ID (used by frontend on startup)."""
    result = await db.execute(
        select(DisplayPosition).where(DisplayPosition.display_id == display_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"Display '{display_id}' not found")
    return row


@router.post("/", response_model=schemas.DisplayOut, status_code=201)
async def create_display(
    body: schemas.DisplayCreate,
    db: AsyncSession = Depends(get_db),
    _auth: AuthUser = Depends(optional_auth),
):
    """Register a new display on the floor plan."""
    existing = await db.execute(
        select(DisplayPosition).where(DisplayPosition.display_id == body.display_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Display '{body.display_id}' already exists")

    row = DisplayPosition(
        display_id=body.display_id,
        display_name=body.display_name,
        zone=body.zone,
        x=body.x,
        y=body.y,
        screen_width_px=body.screen_width_px,
        screen_height_px=body.screen_height_px,
        sort_order=body.sort_order,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("Display registered: %s at (%s, %s) in zone %s", body.display_id, body.x, body.y, body.zone)
    return row


@router.put("/{display_id}", response_model=schemas.DisplayOut)
async def update_display(
    display_id: str,
    body: schemas.DisplayUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: AuthUser = Depends(optional_auth),
):
    """Update display position/settings."""
    result = await db.execute(
        select(DisplayPosition).where(DisplayPosition.display_id == display_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"Display '{display_id}' not found")

    for field in ("display_name", "zone", "x", "y", "screen_width_px", "screen_height_px", "sort_order"):
        if field in body.model_fields_set:
            setattr(row, field, getattr(body, field))

    await db.commit()
    await db.refresh(row)
    logger.info("Display updated: %s", display_id)
    return row


@router.delete("/{display_id}", status_code=204)
async def delete_display(
    display_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: AuthUser = Depends(optional_auth),
):
    """Remove a display from the floor plan."""
    result = await db.execute(
        select(DisplayPosition).where(DisplayPosition.display_id == display_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Display '{display_id}' not found")

    await db.execute(
        sa_delete(DisplayPosition).where(DisplayPosition.display_id == display_id)
    )
    await db.commit()
    logger.info("Display removed: %s", display_id)


@router.put("/{display_id}/heartbeat", response_model=schemas.DisplayOut)
async def display_heartbeat(
    display_id: str,
    body: schemas.DisplayHeartbeat,
    db: AsyncSession = Depends(get_db),
):
    """Update last_seen_at and optional screen dimensions."""
    result = await db.execute(
        select(DisplayPosition).where(DisplayPosition.display_id == display_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail=f"Display '{display_id}' not found")

    row.last_seen_at = datetime.now(timezone.utc)
    row.is_active = True
    if body.screen_width_px is not None:
        row.screen_width_px = body.screen_width_px
    if body.screen_height_px is not None:
        row.screen_height_px = body.screen_height_px

    await db.commit()
    await db.refresh(row)
    return row
