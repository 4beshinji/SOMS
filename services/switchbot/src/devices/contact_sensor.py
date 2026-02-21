"""SwitchBot Contact Sensor device."""

from .base import SwitchBotDevice


class ContactSensorDevice(SwitchBotDevice):
    device_type = "contact_sensor"

    def status_to_channels(self, status: dict) -> dict:
        channels = {}
        if "openState" in status:
            # "open", "close", "timeOutNotClose"
            channels["door"] = 0 if status["openState"] == "close" else 1
        if "moveDetected" in status:
            channels["motion"] = 1 if status["moveDetected"] else 0
        if "battery" in status:
            channels["battery"] = status["battery"]
        return channels
