"""SwitchBot Ceiling Light / Strip Light device."""

import asyncio
import logging

from .base import SwitchBotDevice

logger = logging.getLogger(__name__)


class LightDevice(SwitchBotDevice):
    device_type = "light"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_tool("turn_on", self._turn_on)
        self.register_tool("turn_off", self._turn_off)
        self.register_tool("set_brightness", self._set_brightness)
        self.register_tool("set_color", self._set_color)

    def status_to_channels(self, status: dict) -> dict:
        channels = {}
        if "power" in status:
            channels["power_state"] = 1 if status["power"] == "on" else 0
        if "brightness" in status:
            channels["brightness"] = status["brightness"]
        if "color" in status:
            channels["color"] = status["color"]
        return channels

    def _turn_on(self):
        asyncio.ensure_future(self._api.send_command(self.switchbot_id, "turnOn"))
        return {"status": "ok", "command": "turnOn"}

    def _turn_off(self):
        asyncio.ensure_future(self._api.send_command(self.switchbot_id, "turnOff"))
        return {"status": "ok", "command": "turnOff"}

    def _set_brightness(self, brightness: int = 100):
        asyncio.ensure_future(
            self._api.send_command(self.switchbot_id, "setBrightness", str(brightness))
        )
        return {"status": "ok", "command": "setBrightness", "brightness": brightness}

    def _set_color(self, r: int = 255, g: int = 255, b: int = 255):
        asyncio.ensure_future(
            self._api.send_command(self.switchbot_id, "setColor", f"{r}:{g}:{b}")
        )
        return {"status": "ok", "command": "setColor", "color": f"{r}:{g}:{b}"}
