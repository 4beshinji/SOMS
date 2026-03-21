"""PostgreSQL implementation of SpatialDataRepository.

Queries events.spatial_snapshots and events.spatial_heatmap_hourly,
and reads spatial config from config/spatial.yaml.
Merges DB-stored device_positions into the config (DB wins on conflict).
"""
import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from spatial_config import load_spatial_config
from models import DevicePosition, CameraPosition
from .spatial_repository import (
    HeatmapData,
    LiveSpatialData,
    SpatialConfigResponse,
    SpatialDataRepository,
)

logger = logging.getLogger(__name__)


class PgSpatialRepository(SpatialDataRepository):

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_spatial_config(self) -> SpatialConfigResponse:
        config = load_spatial_config()

        # Start with YAML devices
        devices = {
            dev_id: asdict(dev)
            for dev_id, dev in config.devices.items()
        }

        # Merge DB device_positions (DB wins on same device_id)
        try:
            result = await self._session.execute(select(DevicePosition))
            for row in result.scalars().all():
                try:
                    channels = json.loads(row.channels) if row.channels else []
                except (json.JSONDecodeError, TypeError):
                    channels = []
                devices[row.device_id] = {
                    "zone": row.zone,
                    "position": [row.x, row.y],
                    "type": row.device_type or "sensor",
                    "channels": channels,
                    "orientation_deg": row.orientation_deg,
                    "fov_deg": row.fov_deg,
                    "detection_range_m": row.detection_range_m,
                }
        except Exception:
            logger.warning("Could not read device_positions table (may not exist yet)")

        # Start with YAML cameras
        cameras = {
            cam_id: asdict(cam)
            for cam_id, cam in config.cameras.items()
        }

        # Merge DB camera_positions (DB wins on same camera_id)
        try:
            result = await self._session.execute(select(CameraPosition))
            for row in result.scalars().all():
                cam = cameras.get(row.camera_id, {})
                cam.update({k: v for k, v in {
                    "zone": row.zone,
                    "position": [row.x, row.y, row.z] if row.z is not None else [row.x, row.y],
                    "fov_deg": row.fov_deg,
                    "orientation_deg": row.orientation_deg,
                }.items() if v is not None})
                cameras[row.camera_id] = cam
        except Exception:
            logger.warning("Could not read camera_positions table (may not exist yet)")

        return SpatialConfigResponse(
            building=asdict(config.building),
            zones={
                zone_id: asdict(geom)
                for zone_id, geom in config.zones.items()
            },
            devices=devices,
            cameras=cameras,
        )

    async def get_live_spatial(
        self, zone: str | None = None
    ) -> list[LiveSpatialData]:
        result = await self._session.execute(
            text("""
                SELECT DISTINCT ON (zone)
                    timestamp, zone, camera_id, data
                FROM events.spatial_snapshots
                WHERE timestamp > now() - interval '30 seconds'
                  AND (CAST(:zone AS TEXT) IS NULL OR zone = :zone)
                ORDER BY zone, timestamp DESC
            """),
            {"zone": zone},
        )
        items = []
        for row in result.fetchall():
            data = row[3] if isinstance(row[3], dict) else json.loads(row[3])
            items.append(LiveSpatialData(
                zone=row[1],
                camera_id=row[2],
                timestamp=row[0],
                image_size=data.get("image_size", [640, 480]),
                persons=data.get("persons", []),
                objects=data.get("objects", []),
            ))
        return items

    async def get_heatmap(
        self, zone: str | None = None, period: str = "hour"
    ) -> list[HeatmapData]:
        # Determine time window
        now = datetime.now(timezone.utc)
        if period == "day":
            start = now - timedelta(days=1)
        elif period == "week":
            start = now - timedelta(weeks=1)
        else:
            start = now - timedelta(hours=1)

        result = await self._session.execute(
            text("""
                SELECT zone, period_start, grid_cols, grid_rows,
                       cell_counts, person_count_avg
                FROM events.spatial_heatmap_hourly
                WHERE period_start >= :start
                  AND (CAST(:zone AS TEXT) IS NULL OR zone = :zone)
                ORDER BY zone, period_start ASC
            """),
            {"start": start, "zone": zone},
        )

        # Aggregate across the time window per zone
        zone_data: dict[str, HeatmapData] = {}
        for row in result.fetchall():
            z = row[0]
            cols = row[2]
            rows = row[3]
            cell_counts = row[4] if isinstance(row[4], list) else json.loads(row[4])
            avg_persons = row[5]

            if z not in zone_data:
                zone_data[z] = HeatmapData(
                    zone=z,
                    period=period,
                    grid_cols=cols,
                    grid_rows=rows,
                    cell_counts=[[0] * cols for _ in range(rows)],
                    person_count_avg=0.0,
                    period_start=row[1],
                    period_end=now,
                )

            hm = zone_data[z]
            # Sum cell counts across hourly buckets
            for r_idx, row_counts in enumerate(cell_counts):
                if r_idx < len(hm.cell_counts):
                    for c_idx, cnt in enumerate(row_counts):
                        if c_idx < len(hm.cell_counts[r_idx]):
                            hm.cell_counts[r_idx][c_idx] += cnt
            hm.person_count_avg = max(hm.person_count_avg, avg_persons)

        return list(zone_data.values())
