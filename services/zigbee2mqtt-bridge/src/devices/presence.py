"""Zigbee2MQTT 24GHz human presence sensor device (e.g. HOBEIAN ZG-204ZK)."""

from .base import ZigbeeDevice


class PresenceDevice(ZigbeeDevice):
    device_type = "presence"
    channel_aggregation = {"motion": "latest"}

    def state_to_channels(self, state: dict) -> dict:
        channels = {}
        if "presence" in state:
            channels["motion"] = 1 if state["presence"] else 0
        return channels
