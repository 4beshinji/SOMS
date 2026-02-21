"""SwitchBot Bot device."""

import logging

from .base import SwitchBotDevice

logger = logging.getLogger(__name__)


class BotDevice(SwitchBotDevice):
    device_type = "bot"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_tool("turn_on", self._turn_on)
        self.register_tool("turn_off", self._turn_off)
        self.register_tool("press", self._press)

    def status_to_channels(self, status: dict) -> dict:
        channels = {}
        if "power" in status:
            channels["power_state"] = 1 if status["power"] == "on" else 0
        if "battery" in status:
            channels["battery"] = status["battery"]
        return channels

    def _turn_on(self):
        import asyncio
        asyncio.ensure_future(self._api.send_command(self.switchbot_id, "turnOn"))
        return {"status": "ok", "command": "turnOn"}

    def _turn_off(self):
        import asyncio
        asyncio.ensure_future(self._api.send_command(self.switchbot_id, "turnOff"))
        return {"status": "ok", "command": "turnOff"}

    def _press(self):
        import asyncio
        asyncio.ensure_future(self._api.send_command(self.switchbot_id, "press"))
        return {"status": "ok", "command": "press"}
