"""
Inventory Items API — CRUD for shelf sensor → item mappings,
plus live status computed from latest sensor readings.
"""
import logging
import time
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import InventoryItem
from schemas import (
    InventoryItemCreate, InventoryItemUpdate, InventoryItemResponse,
    InventoryLiveItem, InventoryLiveStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory", tags=["inventory"])


# --- Live Inventory Status (computed from DB sensor data + config) ---

@router.get("/live-status", response_model=InventoryLiveStatusResponse)
async def get_live_inventory_status(db: AsyncSession = Depends(get_db)):
    """Compute live inventory status from latest sensor readings + config.

    Rule-based: qty = int(latest_weight / unit_weight_g).
    No Brain dependency — reads directly from events.raw_events.
    """
    # 1. Load active inventory items
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.is_active == True)
    )
    items = result.scalars().all()
    if not items:
        return InventoryLiveStatusResponse(items=[], updated_at=time.time())

    # 2. For each item, get latest weight from raw_events
    live_items = []
    latest_ts = 0.0

    for item in items:
        row = (await db.execute(text("""
            SELECT data->>'value' as weight, timestamp
            FROM events.raw_events
            WHERE source_device = :device_id
              AND event_type = 'sensor_reading'
              AND data->>'channel' = :channel
            ORDER BY timestamp DESC
            LIMIT 1
        """), {"device_id": item.device_id, "channel": item.channel})).first()

        if row is None:
            continue

        try:
            weight = float(row.weight)
        except (TypeError, ValueError):
            continue

        ts = row.timestamp.timestamp() if row.timestamp else 0.0
        if ts > latest_ts:
            latest_ts = ts

        # Rule: qty = int((weight - tare) / unit_weight)
        net = weight - item.tare_weight_g
        qty = max(0, int(net / item.unit_weight_g)) if item.unit_weight_g > 0 else 0
        status = "low" if qty < item.min_threshold else "ok"

        live_items.append(InventoryLiveItem(
            device_id=item.device_id,
            channel=item.channel,
            zone=item.zone,
            item_name=item.item_name,
            category=item.category,
            quantity=qty,
            min_threshold=item.min_threshold,
            current_weight_g=round(weight, 1),
            status=status,
            barcode=item.barcode,
        ))

    return InventoryLiveStatusResponse(items=live_items, updated_at=latest_ts or time.time())


# --- CRUD ---

@router.get("/", response_model=list[InventoryItemResponse])
async def list_inventory_items(
    zone: Optional[str] = None,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """List inventory items, optionally filtered by zone."""
    query = select(InventoryItem)
    if zone:
        query = query.where(InventoryItem.zone == zone)
    if active_only:
        query = query.where(InventoryItem.is_active == True)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{item_id}", response_model=InventoryItemResponse)
async def get_inventory_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single inventory item by ID."""
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return item


@router.post("/", response_model=InventoryItemResponse, status_code=201)
async def create_inventory_item(
    data: InventoryItemCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new inventory item (shelf sensor → item mapping)."""
    item = InventoryItem(**data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    logger.info("Inventory item created: %s on %s", data.item_name, data.device_id)
    return item


@router.put("/{item_id}", response_model=InventoryItemResponse)
async def update_inventory_item(
    item_id: int,
    data: InventoryItemUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing inventory item."""
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
async def delete_inventory_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an inventory item."""
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    await db.delete(item)
    await db.commit()
