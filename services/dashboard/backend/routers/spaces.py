"""Spaces API — unified spatial information endpoint.

Consolidates /sensors/spatial/* (read) and /devices/positions/* (write)
under a coherent /spaces/{zone} hierarchy.

Three-layer model:
  Layer 1 — Topology   (YAML, git-managed): zone polygons, building dims, ArUco
  Layer 2 — Placement  (DB, UI-editable):   device/camera positions
  Layer 3 — Observations (events.*):        live detections, heatmaps

Backward-compatible: /sensors/spatial/* routes remain active.
"""
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import DevicePosition, CameraPosition
from repositories.deps import get_spatial_repo
from repositories.spatial_repository import SpatialDataRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/spaces", tags=["spaces"])


# ── Response Models ──────────────────────────────────────────────────


class ZoneSummary(BaseModel):
    zone_id: str
    display_name: str = ""
    floor: int = 1
    area_m2: float = 0.0
    adjacent_zones: list[str] = []


class ZoneDetailResponse(BaseModel):
    """Full zone snapshot: Layer 1 (topology) + Layer 2 (placement) + Layer 3 summary."""
    zone_id: str
    display_name: str = ""
    floor: int = 1
    area_m2: float = 0.0
    polygon: list[list[float]] = []
    adjacent_zones: list[str] = []
    grid_cols: int = 10
    grid_rows: int = 10
    devices: dict[str, Any] = {}
    cameras: dict[str, Any] = {}


class LiveSpatialResponse(BaseModel):
    zone: str
    camera_id: str | None = None
    timestamp: str | None = None
    image_size: list[int] = [640, 480]
    persons: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []


class HeatmapResponse(BaseModel):
    zone: str
    period: str = "hour"
    grid_cols: int = 10
    grid_rows: int = 10
    cell_counts: list[list[int]] = []
    person_count_avg: float = 0.0
    period_start: str | None = None
    period_end: str | None = None


class UpdateDeviceIn(BaseModel):
    x: float
    y: float
    zone: str | None = None


class UpsertCameraIn(BaseModel):
    x: float
    y: float
    z: float | None = None
    fov_deg: float | None = None
    orientation_deg: float | None = None


# ── Read Endpoints ───────────────────────────────────────────────────


@router.get("", response_model=list[ZoneSummary])
async def list_zones(
    repo: SpatialDataRepository = Depends(get_spatial_repo),
):
    """All zones — ID, display name, floor, area."""
    config = await repo.get_spatial_config()
    return [
        ZoneSummary(
            zone_id=zone_id,
            display_name=geom.get("display_name", ""),
            floor=geom.get("floor", 1),
            area_m2=geom.get("area_m2", 0.0),
            adjacent_zones=geom.get("adjacent_zones", []),
        )
        for zone_id, geom in config.zones.items()
    ]


@router.get("/{zone_id}", response_model=ZoneDetailResponse)
async def get_zone(
    zone_id: str,
    repo: SpatialDataRepository = Depends(get_spatial_repo),
):
    """Full zone detail: topology + device/camera placements."""
    config = await repo.get_spatial_config()
    if zone_id not in config.zones:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    geom = config.zones[zone_id]
    zone_devices = {
        dev_id: dev
        for dev_id, dev in config.devices.items()
        if dev.get("zone") == zone_id
    }
    zone_cameras = {
        cam_id: cam
        for cam_id, cam in config.cameras.items()
        if cam.get("zone") == zone_id
    }
    return ZoneDetailResponse(
        zone_id=zone_id,
        display_name=geom.get("display_name", ""),
        floor=geom.get("floor", 1),
        area_m2=geom.get("area_m2", 0.0),
        polygon=geom.get("polygon", []),
        adjacent_zones=geom.get("adjacent_zones", []),
        grid_cols=geom.get("grid_cols", 10),
        grid_rows=geom.get("grid_rows", 10),
        devices=zone_devices,
        cameras=zone_cameras,
    )


@router.get("/{zone_id}/live", response_model=list[LiveSpatialResponse])
async def get_zone_live(
    zone_id: str,
    repo: SpatialDataRepository = Depends(get_spatial_repo),
):
    """Real-time person/object detections in zone (Layer 3)."""
    data = await repo.get_live_spatial(zone=zone_id)
    return [
        LiveSpatialResponse(
            zone=d.zone,
            camera_id=d.camera_id,
            timestamp=d.timestamp.isoformat() if d.timestamp else None,
            image_size=d.image_size,
            persons=d.persons,
            objects=d.objects,
        )
        for d in data
    ]


@router.get("/{zone_id}/heatmap", response_model=list[HeatmapResponse])
async def get_zone_heatmap(
    zone_id: str,
    period: str = Query("hour", description="hour | day | week"),
    repo: SpatialDataRepository = Depends(get_spatial_repo),
):
    """Occupancy heatmap for zone (Layer 3)."""
    data = await repo.get_heatmap(zone=zone_id, period=period)
    return [
        HeatmapResponse(
            zone=d.zone,
            period=d.period,
            grid_cols=d.grid_cols,
            grid_rows=d.grid_rows,
            cell_counts=d.cell_counts,
            person_count_avg=d.person_count_avg,
            period_start=d.period_start.isoformat() if d.period_start else None,
            period_end=d.period_end.isoformat() if d.period_end else None,
        )
        for d in data
    ]


# ── Write Endpoints (Layer 2 — Placement) ───────────────────────────


@router.put("/{zone_id}/devices/{device_id}", status_code=200)
async def update_device_placement(
    zone_id: str,
    device_id: str,
    body: UpdateDeviceIn,
    db: AsyncSession = Depends(get_db),
):
    """Update device position within zone (creates DB override if not exists)."""
    result = await db.execute(
        select(DevicePosition).where(DevicePosition.device_id == device_id)
    )
    row = result.scalar_one_or_none()
    if row:
        row.x = body.x
        row.y = body.y
        row.zone = zone_id
    else:
        row = DevicePosition(
            device_id=device_id,
            zone=zone_id,
            x=body.x,
            y=body.y,
            channels=json.dumps([]),
        )
        db.add(row)
    await db.commit()
    logger.info("Device %s placed at (%s, %s) in zone %s", device_id, body.x, body.y, zone_id)
    return {"device_id": device_id, "zone": zone_id, "x": body.x, "y": body.y}


@router.put("/{zone_id}/cameras/{camera_id}", status_code=200)
async def update_camera_placement(
    zone_id: str,
    camera_id: str,
    body: UpsertCameraIn,
    db: AsyncSession = Depends(get_db),
):
    """Update camera position/FOV within zone (upsert DB override)."""
    result = await db.execute(
        select(CameraPosition).where(CameraPosition.camera_id == camera_id)
    )
    row = result.scalar_one_or_none()
    if row:
        row.zone = zone_id
        row.x = body.x
        row.y = body.y
        row.z = body.z
        row.fov_deg = body.fov_deg
        row.orientation_deg = body.orientation_deg
    else:
        row = CameraPosition(
            camera_id=camera_id,
            zone=zone_id,
            x=body.x,
            y=body.y,
            z=body.z,
            fov_deg=body.fov_deg,
            orientation_deg=body.orientation_deg,
        )
        db.add(row)
    await db.commit()
    logger.info("Camera %s placed at (%s, %s) in zone %s", camera_id, body.x, body.y, zone_id)
    return {"camera_id": camera_id, "zone": zone_id, "x": body.x, "y": body.y}


@router.delete("/{zone_id}/devices/{device_id}/override", status_code=204)
async def reset_device_placement(
    zone_id: str,
    device_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove DB override for device — reverts to YAML default."""
    await db.execute(
        sa_delete(DevicePosition).where(DevicePosition.device_id == device_id)
    )
    await db.commit()
    logger.info("Device override removed: %s (reverted to YAML)", device_id)


@router.delete("/{zone_id}/cameras/{camera_id}/override", status_code=204)
async def reset_camera_placement(
    zone_id: str,
    camera_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove DB override for camera — reverts to YAML default."""
    await db.execute(
        sa_delete(CameraPosition).where(CameraPosition.camera_id == camera_id)
    )
    await db.commit()
    logger.info("Camera override removed: %s (reverted to YAML)", camera_id)
