"""
Spatial configuration loader for SOMS office layout.

Loads zone geometry, device positions, and camera positions from
config/spatial.yaml. Used by WorldModel to attach spatial metadata
to zones and by the dashboard to render floor plans.
"""
import os
from dataclasses import dataclass, field
from typing import Optional

import yaml
from loguru import logger


@dataclass
class BuildingConfig:
    name: str = "SOMS Office"
    width_m: float = 15.0
    height_m: float = 10.0
    floor_plan_image: Optional[str] = None


@dataclass
class ZoneGeometry:
    display_name: str = ""
    polygon: list[list[float]] = field(default_factory=list)
    area_m2: float = 0.0
    floor: int = 1
    adjacent_zones: list[str] = field(default_factory=list)
    grid_cols: int = 10
    grid_rows: int = 10


@dataclass
class DevicePosition:
    zone: str = ""
    position: list[float] = field(default_factory=lambda: [0.0, 0.0])
    type: str = "sensor"
    channels: list[str] = field(default_factory=list)
    orientation_deg: Optional[float] = None
    fov_deg: Optional[float] = None
    detection_range_m: Optional[float] = None


@dataclass
class CameraConfig:
    zone: str = ""
    position: list[float] = field(default_factory=lambda: [0.0, 0.0])
    resolution: list[int] = field(default_factory=lambda: [640, 480])
    fov_deg: float = 90.0
    orientation_deg: float = 0.0


@dataclass
class SpatialConfig:
    building: BuildingConfig = field(default_factory=BuildingConfig)
    zones: dict[str, ZoneGeometry] = field(default_factory=dict)
    devices: dict[str, DevicePosition] = field(default_factory=dict)
    cameras: dict[str, CameraConfig] = field(default_factory=dict)


def load_spatial_config(path: str = "config/spatial.yaml") -> SpatialConfig:
    """Load spatial configuration from YAML file.

    Falls back to an empty SpatialConfig if the file doesn't exist,
    so the system can run without spatial data.
    """
    if not os.path.exists(path):
        logger.warning("Spatial config not found at {}, using defaults", path)
        return SpatialConfig()

    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}

    config = SpatialConfig()

    # Building
    bld = raw.get("building", {})
    config.building = BuildingConfig(
        name=bld.get("name", "SOMS Office"),
        width_m=bld.get("width_m", 15.0),
        height_m=bld.get("height_m", 10.0),
        floor_plan_image=bld.get("floor_plan_image"),
    )

    # Zones
    for zone_id, zdata in raw.get("zones", {}).items():
        config.zones[zone_id] = ZoneGeometry(
            display_name=zdata.get("display_name", zone_id),
            polygon=zdata.get("polygon", []),
            area_m2=zdata.get("area_m2", 0.0),
            floor=zdata.get("floor", 1),
            adjacent_zones=zdata.get("adjacent_zones", []),
            grid_cols=zdata.get("grid_cols", 10),
            grid_rows=zdata.get("grid_rows", 10),
        )

    # Devices
    for dev_id, ddata in raw.get("devices", {}).items():
        config.devices[dev_id] = DevicePosition(
            zone=ddata.get("zone", ""),
            position=ddata.get("position", [0.0, 0.0]),
            type=ddata.get("type", "sensor"),
            channels=ddata.get("channels", []),
            orientation_deg=ddata.get("orientation_deg"),
            fov_deg=ddata.get("fov_deg"),
            detection_range_m=ddata.get("detection_range_m"),
        )

    # Cameras
    for cam_id, cdata in raw.get("cameras", {}).items():
        config.cameras[cam_id] = CameraConfig(
            zone=cdata.get("zone", ""),
            position=cdata.get("position", [0.0, 0.0]),
            resolution=cdata.get("resolution", [640, 480]),
            fov_deg=cdata.get("fov_deg", 90.0),
            orientation_deg=cdata.get("orientation_deg", 0.0),
        )

    logger.info(
        "Spatial config loaded: {} zones, {} devices, {} cameras",
        len(config.zones), len(config.devices), len(config.cameras),
    )
    return config
