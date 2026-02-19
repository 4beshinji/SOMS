"""Abstract base class for spatial data repositories.

Backend-agnostic interface for spatial map data access.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel


# ── Shared Data Models ──────────────────────────────────────────────


class SpatialConfigResponse(BaseModel):
    """Building + zone geometry + device/camera positions."""
    building: dict[str, Any] = {}
    zones: dict[str, Any] = {}
    devices: dict[str, Any] = {}
    cameras: dict[str, Any] = {}


class LiveSpatialData(BaseModel):
    """Real-time spatial detection snapshot for a zone."""
    zone: str
    camera_id: str | None = None
    timestamp: datetime | None = None
    image_size: list[int] = [640, 480]
    persons: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []


class HeatmapData(BaseModel):
    """Heatmap grid data for a zone over a time period."""
    zone: str
    period: str = "hour"
    grid_cols: int = 10
    grid_rows: int = 10
    cell_counts: list[list[int]] = []
    person_count_avg: float = 0.0
    period_start: datetime | None = None
    period_end: datetime | None = None


# ── Abstract Repository ─────────────────────────────────────────────


class SpatialDataRepository(ABC):

    @abstractmethod
    async def get_spatial_config(self) -> SpatialConfigResponse:
        """Zone shapes, device positions, camera positions from config."""

    @abstractmethod
    async def get_live_spatial(
        self, zone: str | None = None
    ) -> list[LiveSpatialData]:
        """Real-time person/object positions from latest spatial snapshots."""

    @abstractmethod
    async def get_heatmap(
        self, zone: str | None = None, period: str = "hour"
    ) -> list[HeatmapData]:
        """Heatmap data aggregated by time period."""
