"""SwitchBot device type registry."""

from .meter import MeterDevice
from .motion_sensor import MotionSensorDevice
from .contact_sensor import ContactSensorDevice
from .bot import BotDevice
from .curtain import CurtainDevice
from .plug import PlugDevice
from .lock import LockDevice
from .light import LightDevice
from .ir_device import IRDevice

DEVICE_TYPE_MAP = {
    "meter": MeterDevice,
    "meter_plus": MeterDevice,
    "motion_sensor": MotionSensorDevice,
    "contact_sensor": ContactSensorDevice,
    "bot": BotDevice,
    "curtain": CurtainDevice,
    "curtain3": CurtainDevice,
    "plug": PlugDevice,
    "plug_mini": PlugDevice,
    "lock": LockDevice,
    "lock_pro": LockDevice,
    "light": LightDevice,
    "ceiling_light": LightDevice,
    "strip_light": LightDevice,
    "ir_ac": IRDevice,
    "ir_tv": IRDevice,
    "ir_fan": IRDevice,
}
