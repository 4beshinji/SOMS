"""Zigbee2MQTT smart plug device."""

import logging

from .base import ZigbeeDevice

logger = logging.getLogger(__name__)


class PlugDevice(ZigbeeDevice):
    device_type = "plug"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_tool("turn_on", self._turn_on)
        self.register_tool("turn_off", self._turn_off)

    def state_to_channels(self, state: dict) -> dict:
        channels = {}
        if "state" in state:
            channels["power_state"] = 1 if state["state"] == "ON" else 0
        if "power" in state:
            channels["wattage"] = state["power"]
        if "voltage" in state:
            channels["voltage"] = state["voltage"]
        if "current" in state:
            channels["current"] = state["current"]
        if "energy" in state:
            channels["energy"] = state["energy"]
        return channels

    def _turn_on(self):
        self._publish_z2m_set({"state": "ON"})
        return {"status": "ok", "command": "turn_on"}

    def _turn_off(self):
        self._publish_z2m_set({"state": "OFF"})
        return {"status": "ok", "command": "turn_off"}
