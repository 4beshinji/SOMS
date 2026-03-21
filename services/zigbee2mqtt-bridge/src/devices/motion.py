"""Zigbee2MQTT motion sensor device."""

from .base import ZigbeeDevice


class MotionDevice(ZigbeeDevice):
    device_type = "motion"
    channel_aggregation = {"motion": "count"}

    def state_to_channels(self, state: dict) -> dict:
        channels = {}
        if "occupancy" in state:
            # Z2M uses "occupancy" (bool) — convert to motion 0/1
            channels["motion"] = 1 if state["occupancy"] else 0
        if "illuminance" in state:
            channels["illuminance"] = state["illuminance"]
        if "illuminance_lux" in state:
            channels["illuminance"] = state["illuminance_lux"]
        return channels
