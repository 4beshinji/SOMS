"""Zigbee2MQTT temperature/humidity sensor device."""

from .base import ZigbeeDevice


class TempHumidityDevice(ZigbeeDevice):
    device_type = "temp_humidity"

    def state_to_channels(self, state: dict) -> dict:
        channels = {}
        if "temperature" in state:
            channels["temperature"] = state["temperature"]
        if "humidity" in state:
            channels["humidity"] = state["humidity"]
        if "pressure" in state:
            channels["pressure"] = state["pressure"]
        return channels
