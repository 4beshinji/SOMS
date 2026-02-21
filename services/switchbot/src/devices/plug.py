"""SwitchBot Plug / PlugMini device."""

import asyncio
import logging

from .base import SwitchBotDevice

logger = logging.getLogger(__name__)


class PlugDevice(SwitchBotDevice):
    device_type = "plug"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_tool("turn_on", self._turn_on)
        self.register_tool("turn_off", self._turn_off)

    def status_to_channels(self, status: dict) -> dict:
        channels = {}
        if "power" in status:
            channels["power_state"] = 1 if status["power"] == "on" else 0
        if "weight" in status:
            # SwitchBot reports wattage as "weight" in some FW versions
            channels["wattage"] = status["weight"]
        if "electricCurrent" in status:
            channels["wattage"] = status["electricCurrent"]
        if "voltage" in status:
            channels["voltage"] = status["voltage"]
        return channels

    def _turn_on(self):
        asyncio.ensure_future(self._api.send_command(self.switchbot_id, "turnOn"))
        return {"status": "ok", "command": "turnOn"}

    def _turn_off(self):
        asyncio.ensure_future(self._api.send_command(self.switchbot_id, "turnOff"))
        return {"status": "ok", "command": "turnOff"}
