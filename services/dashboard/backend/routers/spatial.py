"""Spatial Map API — floor plan config, live positions, heatmaps, and zone editor.

Endpoints surface spatial data for the dashboard floor plan view.
"""
import json
import logging
import os
from typing import Any, Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from repositories.deps import get_spatial_repo
from repositories.spatial_repository import SpatialDataRepository
from spatial_config import _cached_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sensors/spatial", tags=["spatial"])

SPATIAL_YAML_PATH = os.environ.get("SPATIAL_CONFIG_PATH", "config/spatial.yaml")
FLOORPLAN_JSON_PATH = os.environ.get("FLOORPLAN_JSON_PATH", "config/floorplan.json")


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


class FloorplanResponse(BaseModel):
    building: dict[str, Any]
    walls: list[dict[str, Any]]
    columns: list[dict[str, Any]]


class ZoneInput(BaseModel):
    display_name: str
    polygon: list[list[float]]
    area_m2: float = 0.0
    floor: int = 1
    adjacent_zones: list[str] = []
    grid_cols: int = 3
    grid_rows: int = 3


class ZonesSaveRequest(BaseModel):
    zones: dict[str, ZoneInput]


class ArucoMarkerInput(BaseModel):
    corners: list[list[float]]  # 4 corners, each [x, y]


class ArucoSaveRequest(BaseModel):
    aruco_markers: dict[str, ArucoMarkerInput]


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


# ── Zone Editor Endpoints ─────────────────────────────────────────


@router.get("/floorplan", response_model=FloorplanResponse)
async def get_floorplan():
    """Serve structural elements (walls, columns) from pre-processed DXF."""
    if not os.path.exists(FLOORPLAN_JSON_PATH):
        raise HTTPException(404, "No floorplan.json found. Run: .venv/bin/python tools/dxf_to_spatial.py")
    with open(FLOORPLAN_JSON_PATH, "r") as f:
        data = json.load(f)
    return FloorplanResponse(
        building=data.get("building", {}),
        walls=data.get("walls", []),
        columns=data.get("columns", []),
    )


@router.get("/zones")
async def get_zones():
    """Get current zone definitions from spatial.yaml."""
    if not os.path.exists(SPATIAL_YAML_PATH):
        return {"zones": {}}
    with open(SPATIAL_YAML_PATH, "r") as f:
        raw = yaml.safe_load(f) or {}
    return {"zones": raw.get("zones", {})}


@router.put("/zones")
async def save_zones(req: ZonesSaveRequest):
    """Save zone definitions to spatial.yaml (preserves other sections)."""
    import spatial_config as sc

    if os.path.exists(SPATIAL_YAML_PATH):
        with open(SPATIAL_YAML_PATH, "r") as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    # Replace zones section
    raw["zones"] = {}
    for zone_id, zone in req.zones.items():
        raw["zones"][zone_id] = {
            "display_name": zone.display_name,
            "polygon": zone.polygon,
            "area_m2": zone.area_m2,
            "floor": zone.floor,
            "adjacent_zones": zone.adjacent_zones,
            "grid_cols": zone.grid_cols,
            "grid_rows": zone.grid_rows,
        }

    with open(SPATIAL_YAML_PATH, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Invalidate cached config
    sc._cached_config = None

    return {"saved": len(req.zones), "path": SPATIAL_YAML_PATH}


# ── ArUco Marker Endpoints ────────────────────────────────────────


@router.get("/aruco")
async def get_aruco_markers():
    """Get ArUco marker definitions from spatial.yaml."""
    if not os.path.exists(SPATIAL_YAML_PATH):
        return {"aruco_markers": {}}
    with open(SPATIAL_YAML_PATH, "r") as f:
        raw = yaml.safe_load(f) or {}
    return {"aruco_markers": raw.get("aruco_markers", {})}


@router.put("/aruco")
async def save_aruco_markers(req: ArucoSaveRequest):
    """Save ArUco marker definitions to spatial.yaml (preserves other sections)."""
    import spatial_config as sc

    if os.path.exists(SPATIAL_YAML_PATH):
        with open(SPATIAL_YAML_PATH, "r") as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    # Replace aruco_markers section
    raw["aruco_markers"] = {}
    for marker_id, marker in req.aruco_markers.items():
        raw["aruco_markers"][marker_id] = {
            "corners": marker.corners,
        }

    with open(SPATIAL_YAML_PATH, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Invalidate cached config
    sc._cached_config = None

    return {"saved": len(req.aruco_markers), "path": SPATIAL_YAML_PATH}
