"""Zigbee2MQTT illuminance (light intensity) sensor device (e.g. HOBEIAN ZG-106Z)."""

from .base import ZigbeeDevice


class IlluminanceDevice(ZigbeeDevice):
    device_type = "illuminance"
    channel_aggregation = {"illuminance": "latest"}

    def state_to_channels(self, state: dict) -> dict:
        channels = {}
        if "illuminance" in state:
            channels["illuminance"] = state["illuminance"]
        if "illuminance_lux" in state:
            channels["illuminance"] = state["illuminance_lux"]
        return channels
