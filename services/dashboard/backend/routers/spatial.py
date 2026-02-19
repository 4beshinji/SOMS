"""Spatial Map API — floor plan config, live positions, and heatmaps.

Endpoints surface spatial data for the dashboard floor plan view.
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from repositories.deps import get_spatial_repo
from repositories.spatial_repository import SpatialDataRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sensors/spatial", tags=["spatial"])


# ── Response Models ─────────────────────────────────────────────────


class SpatialConfigResponse(BaseModel):
    building: dict[str, Any] = {}
    zones: dict[str, Any] = {}
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


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/config", response_model=SpatialConfigResponse)
async def get_spatial_config(
    repo: SpatialDataRepository = Depends(get_spatial_repo),
):
    """Building layout, zone geometry, device and camera positions."""
    config = await repo.get_spatial_config()
    return SpatialConfigResponse(
        building=config.building,
        zones=config.zones,
        devices=config.devices,
        cameras=config.cameras,
    )


@router.get("/live", response_model=list[LiveSpatialResponse])
async def get_live_spatial(
    zone: Optional[str] = Query(None, description="Filter by zone"),
    repo: SpatialDataRepository = Depends(get_spatial_repo),
):
    """Real-time person/object positions from latest spatial snapshots."""
    data = await repo.get_live_spatial(zone=zone)
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


@router.get("/heatmap", response_model=list[HeatmapResponse])
async def get_heatmap(
    zone: Optional[str] = Query(None, description="Filter by zone"),
    period: str = Query("hour", description="Time period: hour, day, week"),
    repo: SpatialDataRepository = Depends(get_spatial_repo),
):
    """Heatmap data for zone(s) aggregated by time period."""
    data = await repo.get_heatmap(zone=zone, period=period)
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
