"""SwitchBot Meter / MeterPlus device."""

from .base import SwitchBotDevice


class MeterDevice(SwitchBotDevice):
    device_type = "meter"

    def status_to_channels(self, status: dict) -> dict:
        channels = {}
        if "temperature" in status:
            channels["temperature"] = status["temperature"]
        if "humidity" in status:
            channels["humidity"] = status["humidity"]
        if "battery" in status:
            channels["battery"] = status["battery"]
        return channels
