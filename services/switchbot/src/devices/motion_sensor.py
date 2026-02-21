"""SwitchBot Motion Sensor device."""

from .base import SwitchBotDevice


class MotionSensorDevice(SwitchBotDevice):
    device_type = "motion_sensor"

    def status_to_channels(self, status: dict) -> dict:
        channels = {}
        if "moveDetected" in status:
            channels["motion"] = 1 if status["moveDetected"] else 0
        if "brightness" in status:
            # SwitchBot returns "bright" or "dim"
            channels["illuminance"] = 1 if status["brightness"] == "bright" else 0
        if "battery" in status:
            channels["battery"] = status["battery"]
        return channels
