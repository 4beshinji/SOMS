"""
Inventory Items API — CRUD for shelf sensor → item mappings.

Used by Brain's InventoryTracker to know what items are on which shelves.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import InventoryItem
from schemas import InventoryItemCreate, InventoryItemUpdate, InventoryItemResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory", tags=["inventory"])


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
