"""Zigbee2MQTT contact (door/window) sensor device."""

from .base import ZigbeeDevice


class ContactDevice(ZigbeeDevice):
    device_type = "contact"

    def state_to_channels(self, state: dict) -> dict:
        channels = {}
        if "contact" in state:
            # Z2M: contact=true means closed, contact=false means open
            # SOMS: door=0 means closed, door=1 means open
            channels["door"] = 0 if state["contact"] else 1
        return channels
