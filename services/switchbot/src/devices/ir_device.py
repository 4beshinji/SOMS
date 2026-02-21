"""SwitchBot IR virtual device (AC, TV, Fan via Hub)."""

import asyncio
import logging

from .base import SwitchBotDevice

logger = logging.getLogger(__name__)


class IRDevice(SwitchBotDevice):
    device_type = "ir_device"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_tool("turn_on", self._turn_on)
        self.register_tool("turn_off", self._turn_off)
        self.register_tool("set_all", self._set_all)

    def status_to_channels(self, status: dict) -> dict:
        # IR devices typically don't report status via Cloud API
        return {}

    def _turn_on(self):
        asyncio.ensure_future(
            self._api.send_command(self.switchbot_id, "turnOn", command_type="command")
        )
        return {"status": "ok", "command": "turnOn"}

    def _turn_off(self):
        asyncio.ensure_future(
            self._api.send_command(self.switchbot_id, "turnOff", command_type="command")
        )
        return {"status": "ok", "command": "turnOff"}

    def _set_all(self, temperature: int = 25, mode: int = 1,
                 fan_speed: int = 1, power_state: str = "on"):
        """Set AC parameters. mode: 1=auto,2=cool,3=dry,4=fan,5=heat.
        fan_speed: 1=auto,2=low,3=medium,4=high.
        power_state: on/off."""
        param = f"{temperature},{mode},{fan_speed},{power_state}"
        asyncio.ensure_future(
            self._api.send_command(self.switchbot_id, "setAll", param, command_type="command")
        )
        return {
            "status": "ok",
            "command": "setAll",
            "temperature": temperature,
            "mode": mode,
            "fan_speed": fan_speed,
            "power_state": power_state,
        }
