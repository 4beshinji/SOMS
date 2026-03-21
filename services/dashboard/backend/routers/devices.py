"""Device Position CRUD API — manage sensor/camera positions on the floor plan."""
import json
import logging
import os
import time
import yaml
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from jwt_auth import AuthUser, require_auth, get_current_user
from models import DevicePosition, CameraPosition

SOMS_ENV = os.environ.get("SOMS_ENV", "development")


async def optional_auth(
    user: AuthUser | None = Depends(get_current_user),
) -> AuthUser:
    """In development mode, allow unauthenticated access with a default editor user."""
    if user is not None:
        return user
    if SOMS_ENV == "development":
        return AuthUser(id=0, username="editor", display_name="Zone Editor")
    raise HTTPException(status_code=401, detail="Authentication required")

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
    orientation_deg: float | None = None
    fov_deg: float | None = None
    detection_range_m: float | None = None


class CreateDevicePositionIn(BaseModel):
    device_id: str
    zone: str
    x: float
    y: float
    device_type: str = "sensor"
    channels: list[str] = []
    orientation_deg: float | None = None
    fov_deg: float | None = None
    detection_range_m: float | None = None

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError("device_id must contain only lowercase letters, digits, and underscores")
        return v


class UpdateDevicePositionIn(BaseModel):
    x: float
    y: float
    zone: str | None = None
    device_type: str | None = None
    channels: list[str] | None = None
    orientation_deg: float | None = None
    fov_deg: float | None = None
    detection_range_m: float | None = None


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
        orientation_deg=row.orientation_deg,
        fov_deg=row.fov_deg,
        detection_range_m=row.detection_range_m,
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
    _auth: AuthUser = Depends(optional_auth),
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
        orientation_deg=body.orientation_deg,
        fov_deg=body.fov_deg,
        detection_range_m=body.detection_range_m,
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
    _auth: AuthUser = Depends(optional_auth),
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
    if body.device_type is not None:
        row.device_type = body.device_type
    if body.channels is not None:
        row.channels = json.dumps(body.channels)
    # For orientation/fov/range: update only if explicitly sent (allows clearing to null)
    if "orientation_deg" in body.model_fields_set:
        row.orientation_deg = body.orientation_deg
    if "fov_deg" in body.model_fields_set:
        row.fov_deg = body.fov_deg
    if "detection_range_m" in body.model_fields_set:
        row.detection_range_m = body.detection_range_m
    await db.commit()
    await db.refresh(row)
    logger.info("Device moved: %s to (%s, %s)", device_id, body.x, body.y)
    return _to_out(row)


@router.delete("/positions/{device_id}", status_code=204)
async def delete_device_position(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: AuthUser = Depends(optional_auth),
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


# ── Discovery Models & Helpers ─────────────────────────────────────


class DiscoveredDevice(BaseModel):
    device_id: str
    source: str           # "config" | "heartbeat" | "both"
    device_type: str
    zone: str | None = None
    label: str | None = None
    channels: list[str] = []
    placed: bool = False
    online: bool | None = None
    battery_pct: int | None = None
    bridge: str | None = None  # "switchbot" | "zigbee2mqtt" | None
    model: str | None = None   # hardware model (e.g. Z2M modelId)


# ── Discovery cache ──────────────────────────────────────────────────
_cached_config: dict[str, Any] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 60.0  # seconds

# Channel mapping for Z2M / SwitchBot device types
_TYPE_CHANNELS: dict[str, list[str]] = {
    "temp_humidity": ["temperature", "humidity"],
    "motion": ["motion", "illuminance"],
    "presence": ["motion"],
    "illuminance": ["illuminance"],
    "contact": ["contact"],
    "plug": ["power_state"],
    "light": ["brightness"],
    "meter": ["temperature", "humidity"],
    "meter_plus": ["temperature", "humidity"],
    "motion_sensor": ["motion"],
    "contact_sensor": ["contact"],
    "bot": ["power_state"],
    "curtain": ["position"],
    "curtain3": ["position"],
    "plug_mini": ["power_state"],
    "lock": ["lock_state"],
    "lock_pro": ["lock_state"],
    "ceiling_light": ["brightness"],
    "strip_light": ["brightness"],
    "ir_ac": ["power_state"],
    "ir_tv": ["power_state"],
    "ir_fan": ["power_state"],
    "vibration": ["vibration"],
    "soil": ["temperature", "humidity"],
    "occupancy": ["occupancy"],
    "pressure": ["pressure"],
    "co2": ["co2"],
    "air_quality": ["pm25", "voc"],
    "water_leak": ["water_leak"],
    "smoke": ["smoke"],
}


def _load_bridge_configs() -> list[dict]:
    """Load device definitions from bridge config YAMLs with caching."""
    global _cached_config, _cache_ts
    now = time.time()
    if now - _cache_ts < _CACHE_TTL and _cached_config:
        return _cached_config.get("devices", [])

    devices: list[dict] = []
    z2m_bridge_devices: list[dict] = []  # raw config entries for cross-reference

    # ZCL Cluster ID → (channel, device_type) mapping
    _ZCL_CLUSTER_MAP: dict[int, tuple[str, str | None]] = {
        1026: ("temperature", "temp_humidity"),
        1029: ("humidity", "temp_humidity"),
        1024: ("illuminance", "illuminance"),
        1028: ("pressure", "pressure"),
        1280: ("motion", "motion"),         # IAS Zone — refined by model override
        1030: ("occupancy", "presence"),
        6:    ("power_state", "plug"),
        8:    ("brightness", "light"),
        768:  ("color", "light"),
        1794: ("power", None),
        2820: ("power", None),
        1027: ("pressure", "pressure"),
        1037: ("co2", "co2"),               # CO2 concentration
        1066: ("pm25", "air_quality"),       # PM2.5
    }

    # Model ID → override device_type (ZCL clusters alone can't distinguish IAS Zone subtypes)
    _MODEL_TYPE_OVERRIDE: dict[str, str] = {
        "ZG-102ZM": "vibration",            # Vibration sensor, not generic motion
        "ZG-303Z":  "soil",                 # Soil moisture (reports temp+humidity via ZCL)
        "ZG-204ZK": "presence",             # 24GHz mmWave presence (IAS Zone → motion, but really presence)
        "ZG-204ZV": "presence",             # 24GHz mmWave multi-sensor
    }

    # Z2M database.db — IEEE → model/manufacturer/capabilities lookup
    z2m_db_models: dict[str, dict] = {}  # ieee_norm → {modelId, manufName, channels, device_type}
    z2m_db_path = Path("/app/z2m-data/database.db")
    if not z2m_db_path.exists():
        z2m_db_path = Path("services/zigbee2mqtt/data/database.db")
    if z2m_db_path.exists():
        try:
            with open(z2m_db_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    ieee = entry.get("ieeeAddr", "")
                    if ieee and entry.get("type") != "Coordinator":
                        ieee_norm = ieee.lower().replace("0x", "")
                        # Collect all inClusters across endpoints
                        all_in: set[int] = set()
                        for ep in entry.get("endpoints", {}).values():
                            all_in.update(ep.get("inClusterList", []))
                        # Derive channels and device_type from ZCL clusters
                        auto_channels: list[str] = []
                        auto_types: list[str] = []
                        for cid in sorted(all_in):
                            mapping = _ZCL_CLUSTER_MAP.get(cid)
                            if mapping:
                                ch, typ = mapping
                                if ch not in auto_channels:
                                    auto_channels.append(ch)
                                if typ and typ not in auto_types:
                                    auto_types.append(typ)
                        # Apply model-based override for IAS Zone subtypes
                        model_id = entry.get("modelId", "")
                        override = _MODEL_TYPE_OVERRIDE.get(model_id)
                        if override:
                            # Replace the primary IAS-derived type with the correct one
                            auto_types = [override if t == "motion" else t for t in auto_types]
                            if override not in auto_types:
                                auto_types.insert(0, override)
                            # Deduplicate
                            seen: list[str] = []
                            for t in auto_types:
                                if t not in seen:
                                    seen.append(t)
                            auto_types = seen

                        z2m_db_models[ieee_norm] = {
                            "modelId": model_id,
                            "manufName": entry.get("manufName", ""),
                            "channels": auto_channels,
                            "device_type": ",".join(auto_types) if auto_types else "sensor",
                        }
        except Exception as e:
            logger.debug("Failed to load z2m database.db: %s", e)

    # Zigbee2MQTT bridge config
    z2m_path = Path("/app/config/zigbee2mqtt-bridge.yaml")
    if not z2m_path.exists():
        z2m_path = Path("config/zigbee2mqtt-bridge.yaml")
    if z2m_path.exists():
        try:
            with open(z2m_path) as f:
                z2m = yaml.safe_load(f) or {}
            z2m_bridge_devices = z2m.get("devices", [])
            for d in z2m_bridge_devices:
                # Lookup model from database.db via IEEE address
                fname = d.get("z2m_friendly_name", "")
                ieee_norm = fname.lower().replace("0x", "")
                db_info = z2m_db_models.get(ieee_norm, {})
                model_str = db_info.get("modelId", "")
                if model_str and db_info.get("manufName"):
                    model_str = f"{db_info['manufName']} {model_str}"
                # Channels: prefer bridge config type mapping, fallback to ZCL auto-detect
                cfg_channels = _TYPE_CHANNELS.get(d.get("type", ""), [])
                zcl_channels = db_info.get("channels", [])
                # Merge: config channels + any ZCL channels not already covered
                merged_channels = list(cfg_channels)
                for ch in zcl_channels:
                    if ch not in merged_channels:
                        merged_channels.append(ch)
                devices.append({
                    "device_id": d.get("soms_device_id", ""),
                    "device_type": d.get("type", "sensor"),
                    "zone": d.get("zone"),
                    "label": d.get("label"),
                    "channels": merged_channels,
                    "bridge": "zigbee2mqtt",
                    "model": model_str or None,
                    "_z2m_friendly_name": fname,  # for dedup in discover_devices
                })
        except Exception as e:
            logger.warning("Failed to load z2m config: %s", e)

    # Z2M configuration.yaml — devices paired to Zigbee but not in bridge config
    z2m_conf_path = Path("/app/z2m-data/configuration.yaml")
    if not z2m_conf_path.exists():
        z2m_conf_path = Path("services/zigbee2mqtt/data/configuration.yaml")
    # Collect both z2m_friendly_name values and their normalized IEEE forms
    registered_z2m_names: set[str] = set()
    for d in z2m_bridge_devices:
        name = d.get("z2m_friendly_name", "")
        if name:
            registered_z2m_names.add(name)
            # Also register normalized IEEE form (lowercase, no 0x prefix)
            registered_z2m_names.add(name.lower().replace("0x", ""))
    if z2m_conf_path.exists():
        try:
            with open(z2m_conf_path) as f:
                z2m_conf = yaml.safe_load(f) or {}
            for ieee, info in (z2m_conf.get("devices") or {}).items():
                fname = info.get("friendly_name", ieee)
                ieee_norm = ieee.replace("'", "").lower().replace("0x", "")
                if fname in registered_z2m_names or ieee_norm in registered_z2m_names:
                    continue  # already in bridge config
                # Auto-generated SOMS ID matches bridge auto_register pattern
                short_ieee = ieee.replace("0x", "").replace("'", "").lower()[-8:]
                db_info = z2m_db_models.get(ieee_norm, {})
                model_str = db_info.get("modelId", "")
                if model_str and db_info.get("manufName"):
                    model_str = f"{db_info['manufName']} {model_str}"
                auto_type = db_info.get("device_type", "sensor")
                auto_channels = db_info.get("channels", [])
                devices.append({
                    "device_id": f"z2m_auto_{short_ieee}",
                    "device_type": auto_type,
                    "zone": None,
                    "label": f"Z2M {fname}",
                    "channels": auto_channels,
                    "bridge": "zigbee2mqtt",
                    "model": model_str or None,
                })
        except Exception as e:
            logger.warning("Failed to load z2m configuration.yaml: %s", e)

    # SwitchBot config
    sb_path = Path("/app/config/switchbot.yaml")
    if not sb_path.exists():
        sb_path = Path("config/switchbot.yaml")
    if sb_path.exists():
        try:
            with open(sb_path) as f:
                sb = yaml.safe_load(f) or {}
            for d in sb.get("devices", []):
                if not d.get("soms_device_id"):
                    continue
                devices.append({
                    "device_id": d.get("soms_device_id", ""),
                    "device_type": d.get("type", "sensor"),
                    "zone": d.get("zone"),
                    "label": d.get("label"),
                    "channels": _TYPE_CHANNELS.get(d.get("type", ""), []),
                    "bridge": "switchbot",
                })
        except Exception as e:
            logger.warning("Failed to load switchbot config: %s", e)

    _cached_config = {"devices": devices}
    _cache_ts = now
    return devices


@router.get("/discovery", response_model=list[DiscoveredDevice])
async def discover_devices(db: AsyncSession = Depends(get_db)):
    """Merge bridge configs + Brain DeviceRegistry snapshot + placed status."""
    # 1. Bridge config devices
    config_devices = _load_bridge_configs()
    merged: dict[str, dict] = {}
    for d in config_devices:
        did = d["device_id"]
        if not did:
            continue
        merged[did] = {
            "device_id": did,
            "source": "config",
            "device_type": d["device_type"],
            "zone": d.get("zone"),
            "label": d.get("label"),
            "channels": d.get("channels", []),
            "placed": False,
            "online": None,
            "battery_pct": None,
            "bridge": d.get("bridge"),
            "model": d.get("model"),
        }

    # Build set of known IEEE suffixes from all z2m config devices for dedup.
    # Covers both z2m_auto_ IDs and bridge-registered IDs whose IEEE suffix
    # may appear as stale z2m_auto_ entries in Brain's DeviceRegistry snapshot.
    _known_z2m_suffixes: set[str] = set()
    for d in config_devices:
        if d.get("bridge") != "zigbee2mqtt":
            continue
        did = d.get("device_id", "")
        # z2m_auto_ devices: suffix is the IEEE tail
        if did.startswith("z2m_auto_"):
            _known_z2m_suffixes.add(did.replace("z2m_auto_", ""))
        # Also extract IEEE suffix from raw bridge config z2m_friendly_name
        ieee_raw = d.get("_z2m_friendly_name", "")
        if ieee_raw:
            _known_z2m_suffixes.add(
                ieee_raw.replace("0x", "").replace("'", "").lower()[-8:]
            )

    # 2. Brain DeviceRegistry snapshot (from events.device_registry_snapshot)
    try:
        from sqlalchemy import text as sa_text
        result = await db.execute(
            sa_text("SELECT snapshot FROM events.device_registry_snapshot WHERE id = 1")
        )
        row = result.scalar_one_or_none()
        if row:
            snapshot = json.loads(row) if isinstance(row, str) else row
            for entry in snapshot:
                did = entry.get("device_id", "")
                if not did:
                    continue
                if did in merged:
                    # Overlay online status from brain snapshot
                    merged[did]["online"] = entry.get("state") == "online"
                    merged[did]["battery_pct"] = entry.get("battery_pct")
                    merged[did]["source"] = "both"
                else:
                    # Skip z2m_auto_ heartbeat ghosts whose IEEE suffix
                    # matches a device already registered via bridge config
                    if did.startswith("z2m_auto_"):
                        suffix = did.replace("z2m_auto_", "")
                        if suffix in _known_z2m_suffixes:
                            continue
                    merged[did] = {
                        "device_id": did,
                        "source": "heartbeat",
                        "device_type": entry.get("device_type", "unknown"),
                        "zone": None,
                        "label": None,
                        "channels": entry.get("capabilities", []),
                        "placed": False,
                        "online": entry.get("state") == "online",
                        "battery_pct": entry.get("battery_pct"),
                        "bridge": None,
                    }
    except Exception as e:
        logger.debug("Brain snapshot not available: %s", e)

    # 3. Check which devices are already placed
    placed_result = await db.execute(select(DevicePosition.device_id))
    placed_ids = {row[0] for row in placed_result.all()}
    for did in merged:
        if did in placed_ids:
            merged[did]["placed"] = True

    return [DiscoveredDevice(**v) for v in merged.values()]


# ── Camera Position Endpoints ───────────────────────────────────────


class CameraPositionOut(BaseModel):
    camera_id: str
    zone: str
    x: float
    y: float
    z: float | None = None
    fov_deg: float | None = None
    orientation_deg: float | None = None


class UpsertCameraPositionIn(BaseModel):
    zone: str
    x: float
    y: float
    z: float | None = None
    fov_deg: float | None = None
    orientation_deg: float | None = None


def _cam_to_out(row: CameraPosition) -> CameraPositionOut:
    return CameraPositionOut(
        camera_id=row.camera_id,
        zone=row.zone,
        x=row.x,
        y=row.y,
        z=row.z,
        fov_deg=row.fov_deg,
        orientation_deg=row.orientation_deg,
    )


@router.get("/cameras/", response_model=list[CameraPositionOut])
async def list_camera_positions(db: AsyncSession = Depends(get_db)):
    """List all camera positions (DB overrides only)."""
    result = await db.execute(select(CameraPosition))
    return [_cam_to_out(row) for row in result.scalars().all()]


@router.put("/cameras/{camera_id}", response_model=CameraPositionOut)
async def upsert_camera_position(
    camera_id: str,
    body: UpsertCameraPositionIn,
    db: AsyncSession = Depends(get_db),
    _auth: AuthUser = Depends(optional_auth),
):
    """Create or update camera placement (upsert). Overrides YAML config."""
    result = await db.execute(
        select(CameraPosition).where(CameraPosition.camera_id == camera_id)
    )
    row = result.scalar_one_or_none()
    if row:
        row.zone = body.zone
        row.x = body.x
        row.y = body.y
        row.z = body.z
        row.fov_deg = body.fov_deg
        row.orientation_deg = body.orientation_deg
    else:
        row = CameraPosition(
            camera_id=camera_id,
            zone=body.zone,
            x=body.x,
            y=body.y,
            z=body.z,
            fov_deg=body.fov_deg,
            orientation_deg=body.orientation_deg,
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("Camera upserted: %s at (%s, %s) zone=%s", camera_id, body.x, body.y, body.zone)
    return _cam_to_out(row)


@router.delete("/cameras/{camera_id}", status_code=204)
async def delete_camera_position(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: AuthUser = Depends(optional_auth),
):
    """Remove camera DB override (reverts to YAML default)."""
    result = await db.execute(
        select(CameraPosition).where(CameraPosition.camera_id == camera_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' has no DB override")
    await db.execute(
        sa_delete(CameraPosition).where(CameraPosition.camera_id == camera_id)
    )
    await db.commit()
    logger.info("Camera override removed: %s (reverted to YAML)", camera_id)
