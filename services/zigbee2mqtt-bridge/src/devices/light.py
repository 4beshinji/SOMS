"""Zigbee2MQTT smart light device."""

import logging

from .base import ZigbeeDevice

logger = logging.getLogger(__name__)


class LightDevice(ZigbeeDevice):
    device_type = "light"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_tool("turn_on", self._turn_on)
        self.register_tool("turn_off", self._turn_off)
        self.register_tool("set_brightness", self._set_brightness)
        self.register_tool("set_color_temp", self._set_color_temp)

    def state_to_channels(self, state: dict) -> dict:
        channels = {}
        if "state" in state:
            channels["power_state"] = 1 if state["state"] == "ON" else 0
        if "brightness" in state:
            # Z2M brightness is 0-254, normalize to 0-100
            channels["brightness"] = round(state["brightness"] / 254 * 100)
        if "color_temp" in state:
            channels["color_temp"] = state["color_temp"]
        if "color" in state:
            channels["color"] = state["color"]
        return channels

    def _turn_on(self):
        self._publish_z2m_set({"state": "ON"})
        return {"status": "ok", "command": "turn_on"}

    def _turn_off(self):
        self._publish_z2m_set({"state": "OFF"})
        return {"status": "ok", "command": "turn_off"}

    def _set_brightness(self, brightness: int = 100):
        # Convert 0-100 to Z2M 0-254
        z2m_brightness = round(brightness / 100 * 254)
        self._publish_z2m_set({"brightness": z2m_brightness})
        return {"status": "ok", "command": "set_brightness", "brightness": brightness}

    def _set_color_temp(self, color_temp: int = 370):
        self._publish_z2m_set({"color_temp": color_temp})
        return {"status": "ok", "command": "set_color_temp", "color_temp": color_temp}
