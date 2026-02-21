"""SwitchBot Lock device."""

import asyncio
import logging

from .base import SwitchBotDevice

logger = logging.getLogger(__name__)


class LockDevice(SwitchBotDevice):
    device_type = "lock"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_tool("lock", self._lock)
        self.register_tool("unlock", self._unlock)

    def status_to_channels(self, status: dict) -> dict:
        channels = {}
        if "lockState" in status:
            # "locked" or "unlocked"
            channels["locked"] = 1 if status["lockState"] == "locked" else 0
        if "doorState" in status:
            # "closed" or "opened"
            channels["door"] = 0 if status["doorState"] == "closed" else 1
        if "battery" in status:
            channels["battery"] = status["battery"]
        return channels

    def _lock(self):
        asyncio.ensure_future(self._api.send_command(self.switchbot_id, "lock"))
        return {"status": "ok", "command": "lock"}

    def _unlock(self):
        asyncio.ensure_future(self._api.send_command(self.switchbot_id, "unlock"))
        return {"status": "ok", "command": "unlock"}
