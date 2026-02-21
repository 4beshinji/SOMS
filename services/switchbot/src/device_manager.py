"""Device lifecycle manager: polling, heartbeats, and telemetry orchestration."""

import asyncio
import logging
import time

from switchbot_api import SwitchBotAPI
from mqtt_bridge import MQTTBridge
from devices import DEVICE_TYPE_MAP
from devices.base import SwitchBotDevice

logger = logging.getLogger(__name__)


class DeviceManager:
    """Manages all SwitchBot devices: creation, polling schedules, heartbeats."""

    def __init__(self, config: dict, api: SwitchBotAPI, mqtt: MQTTBridge):
        self._config = config
        self._api = api
        self._mqtt = mqtt
        self._devices: dict[str, SwitchBotDevice] = {}

        polling_cfg = config.get("polling", {})
        self._sensor_interval = polling_cfg.get("sensor_interval_sec", 120)
        self._actuator_interval = polling_cfg.get("actuator_interval_sec", 300)
        self._stagger_ms = polling_cfg.get("stagger_delay_ms", 200)

    def create_devices(self):
        """Instantiate device objects from config."""
        for dev_cfg in self._config.get("devices", []):
            dev_type = dev_cfg.get("type", "")
            cls = DEVICE_TYPE_MAP.get(dev_type)
            if cls is None:
                logger.warning(f"Unknown device type: {dev_type}, skipping {dev_cfg.get('soms_device_id')}")
                continue

            device = cls(
                switchbot_id=dev_cfg["switchbot_id"],
                soms_device_id=dev_cfg["soms_device_id"],
                zone=dev_cfg.get("zone", "main"),
                label=dev_cfg.get("label", ""),
                api=self._api,
                mqtt_bridge=self._mqtt,
            )
            self._devices[device.soms_device_id] = device
            self._mqtt.register_device(device)
            logger.info(f"Created device: {device.soms_device_id} ({dev_type}) -> {device.switchbot_id}")

        logger.info(f"Total devices: {len(self._devices)}")

    @property
    def devices(self) -> dict[str, SwitchBotDevice]:
        return self._devices

    async def poll_loop(self):
        """Main polling loop: fetch status from SwitchBot Cloud, publish telemetry."""
        logger.info("Starting poll loop")
        # Initial poll for all devices
        await self._poll_all()

        while True:
            await asyncio.sleep(self._sensor_interval)
            await self._poll_all()

    async def _poll_all(self):
        """Poll all devices with stagger delay between API calls."""
        stagger = self._stagger_ms / 1000.0
        for device in self._devices.values():
            # Skip actuator-only devices if within actuator interval
            if not device.is_sensor and device._last_poll > 0:
                elapsed = time.time() - device._last_poll
                if elapsed < self._actuator_interval:
                    continue

            await device.poll_status()
            if stagger > 0:
                await asyncio.sleep(stagger)

    async def heartbeat_loop(self):
        """Publish heartbeats every 60 seconds for all devices."""
        logger.info("Starting heartbeat loop")
        while True:
            for device in self._devices.values():
                device.publish_heartbeat()
            await asyncio.sleep(60)
