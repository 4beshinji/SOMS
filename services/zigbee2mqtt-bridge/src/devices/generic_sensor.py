"""Generic Zigbee2MQTT sensor — auto-registered devices with passthrough channels."""

from .base import ZigbeeDevice

# Keys from Z2M payloads that are NOT telemetry channels
_SKIP_KEYS = {
    "battery", "linkquality", "voltage", "last_seen",
    "update", "update_available",
}


class GenericSensorDevice(ZigbeeDevice):
    device_type = "generic_sensor"

    def state_to_channels(self, state: dict) -> dict:
        """Pass through all numeric/bool fields as channels."""
        channels = {}
        for key, value in state.items():
            if key in _SKIP_KEYS:
                continue
            if isinstance(value, (int, float, bool)):
                channels[key] = value
        return channels
