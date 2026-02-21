"""SwitchBot Curtain device."""

import asyncio
import logging

from .base import SwitchBotDevice

logger = logging.getLogger(__name__)


class CurtainDevice(SwitchBotDevice):
    device_type = "curtain"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_tool("open", self._open)
        self.register_tool("close", self._close)
        self.register_tool("set_position", self._set_position)

    def status_to_channels(self, status: dict) -> dict:
        channels = {}
        if "slidePosition" in status:
            channels["position"] = status["slidePosition"]
        if "battery" in status:
            channels["battery"] = status["battery"]
        return channels

    def _open(self):
        asyncio.ensure_future(self._api.send_command(self.switchbot_id, "turnOn"))
        return {"status": "ok", "command": "open"}

    def _close(self):
        asyncio.ensure_future(self._api.send_command(self.switchbot_id, "turnOff"))
        return {"status": "ok", "command": "close"}

    def _set_position(self, position: int = 50):
        index = 0  # default group
        mode = 0   # performance mode
        asyncio.ensure_future(
            self._api.send_command(self.switchbot_id, "setPosition", f"{index},{mode},{position}")
        )
        return {"status": "ok", "command": "setPosition", "position": position}
