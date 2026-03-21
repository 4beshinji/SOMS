"""Device lifecycle manager: creation, heartbeats, and channel aggregation flush."""

import asyncio
import logging
import os

import aiohttp

from mqtt_bridge import MQTTBridge
from devices import DEVICE_TYPE_MAP
from devices.base import ZigbeeDevice
from devices.generic_sensor import GenericSensorDevice

logger = logging.getLogger(__name__)

DEFAULT_FLUSH_INTERVAL = 30


class DeviceManager:
    """Manages all Zigbee2MQTT devices: creation, heartbeats, and flush cycle.

    Unlike SwitchBot DeviceManager, there is no polling loop —
    Z2M pushes state updates over MQTT. Aggregated channels are
    flushed periodically to normalize event frequency for LLM context.
    """

    def __init__(self, config: dict, mqtt: MQTTBridge):
        self._config = config
        self._mqtt = mqtt
        self._devices: dict[str, ZigbeeDevice] = {}
        self._flush_interval = config.get(
            "flush_interval_sec", DEFAULT_FLUSH_INTERVAL
        )

    async def sync_zones_from_spatial(self):
        """Fetch spatial config from dashboard and build device->zone mapping.

        Returns a dict {device_id: zone_id} from the spatial config's device
        positions. This allows ZoneEditor placements to override YAML zone settings.
        """
        backend_url = os.getenv("BACKEND_URL", "http://backend:8000")
        url = f"{backend_url}/sensors/spatial/config"
        mapping: dict[str, dict] = {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        logger.warning("Spatial config fetch failed: %d", resp.status)
                        return mapping
                    data = await resp.json()
            for dev_id, dev_info in (data.get("devices") or {}).items():
                zone = dev_info.get("zone", "")
                label = dev_info.get("label", "")
                # Only use canonical zone IDs (zone_*) — skip legacy names like "main"
                if zone and zone.startswith("zone_"):
                    mapping[dev_id] = {"zone": zone, "label": label}
            logger.info("Spatial config sync: %d device-zone mappings loaded", len(mapping))
        except Exception as e:
            logger.warning("Spatial config sync failed (non-fatal): %s", e)
        return mapping

    def create_devices(self, spatial_overrides: dict | None = None):
        """Instantiate device objects from config.

        Args:
            spatial_overrides: Optional {device_id: {"zone": ..., "label": ...}}
                from spatial config to override YAML zone/label settings.
        """
        overrides = spatial_overrides or {}
        for dev_cfg in self._config.get("devices", []):
            dev_type = dev_cfg.get("type", "")
            cls = DEVICE_TYPE_MAP.get(dev_type)
            if cls is None:
                logger.warning(f"Unknown device type: {dev_type}, skipping {dev_cfg.get('soms_device_id')}")
                continue

            soms_id = dev_cfg["soms_device_id"]
            zone = dev_cfg.get("zone", "main")
            label = dev_cfg.get("label", "")

            # Override from spatial config (ZoneEditor placement)
            if soms_id in overrides:
                override = overrides[soms_id]
                if override.get("zone"):
                    logger.info("Zone override: %s: %s -> %s", soms_id, zone, override["zone"])
                    zone = override["zone"]
                if override.get("label") and not label:
                    label = override["label"]

            device = cls(
                z2m_friendly_name=dev_cfg["z2m_friendly_name"],
                soms_device_id=soms_id,
                zone=zone,
                label=label,
                mqtt_bridge=self._mqtt,
            )
            self._devices[device.soms_device_id] = device
            self._mqtt.register_device(device)
            self._mqtt.register_z2m_device(device.z2m_friendly_name, device)
            logger.info(f"Created device: {device.soms_device_id} ({dev_type}) zone={zone} -> {device.z2m_friendly_name}")

        # Store overrides for auto-registered devices
        self._spatial_overrides = overrides
        logger.info(f"Total devices: {len(self._devices)}")

    @property
    def devices(self) -> dict[str, ZigbeeDevice]:
        return self._devices

    def auto_register(self, z2m_device: dict) -> bool:
        """Auto-register a Z2M device not in config. Returns True if registered.

        Called when bridge/devices reports a device whose friendly_name
        is not in _z2m_name_map. Creates a GenericSensorDevice with an
        auto-generated SOMS ID so telemetry flows into WorldModel immediately.
        """
        friendly_name = z2m_device.get("friendly_name", "")
        if not friendly_name:
            return False
        if z2m_device.get("type") == "Coordinator":
            return False
        # Already registered (by config or previous auto-register)
        if friendly_name in {d.z2m_friendly_name for d in self._devices.values()}:
            return False

        # Generate SOMS device ID from IEEE address or friendly name
        ieee = z2m_device.get("ieee_address", friendly_name)
        soms_id = f"z2m_auto_{ieee.replace('0x', '').lower()[-8:]}"
        # Avoid collision
        if soms_id in self._devices:
            return False

        zone = self._config.get("default_zone", "main")
        definition = z2m_device.get("definition") or {}
        label = definition.get("description", friendly_name)

        # Override from spatial config (ZoneEditor placement)
        overrides = getattr(self, "_spatial_overrides", {})
        if soms_id in overrides:
            override = overrides[soms_id]
            if override.get("zone"):
                zone = override["zone"]
            if override.get("label"):
                label = override["label"]

        device = GenericSensorDevice(
            z2m_friendly_name=friendly_name,
            soms_device_id=soms_id,
            zone=zone,
            label=label,
            mqtt_bridge=self._mqtt,
        )
        self._devices[soms_id] = device
        self._mqtt.register_device(device)
        self._mqtt.register_z2m_device(friendly_name, device)
        logger.info(
            "Auto-registered device: %s (%s) -> %s",
            soms_id, friendly_name, label,
        )
        return True

    def handle_bridge_devices(self, z2m_devices: list[dict]):
        """Process Z2M bridge/devices list — auto-register unknown devices."""
        registered = 0
        for z2m_dev in z2m_devices:
            if self.auto_register(z2m_dev):
                registered += 1
        if registered:
            logger.info("Auto-registered %d new device(s)", registered)

    async def flush_loop(self):
        """Flush aggregated channels periodically.

        Publishes count/latest buffered values for all devices,
        normalizing event frequency so the LLM context receives
        one balanced snapshot per cycle instead of raw event streams.
        """
        logger.info(f"Starting flush loop (interval={self._flush_interval}s)")
        while True:
            await asyncio.sleep(self._flush_interval)
            for device in self._devices.values():
                if device.channel_aggregation:
                    device.flush_channels()

    async def heartbeat_loop(self):
        """Publish heartbeats every 60 seconds for all devices."""
        logger.info("Starting heartbeat loop")
        while True:
            for device in self._devices.values():
                device.publish_heartbeat()
            await asyncio.sleep(60)
