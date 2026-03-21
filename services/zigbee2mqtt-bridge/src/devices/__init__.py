"""Zigbee2MQTT device type registry."""

from .temp_humidity import TempHumidityDevice
from .motion import MotionDevice
from .presence import PresenceDevice
from .illuminance import IlluminanceDevice
from .contact import ContactDevice
from .plug import PlugDevice
from .light import LightDevice
from .generic_sensor import GenericSensorDevice

DEVICE_TYPE_MAP = {
    "temp_humidity": TempHumidityDevice,
    "motion": MotionDevice,
    "presence": PresenceDevice,
    "illuminance": IlluminanceDevice,
    "contact": ContactDevice,
    "plug": PlugDevice,
    "light": LightDevice,
    "generic_sensor": GenericSensorDevice,
}
