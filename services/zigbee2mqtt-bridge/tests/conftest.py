"""Shared fixtures and helpers for Zigbee2MQTT Bridge unit tests."""
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Path setup ──────────────────────────────────────────────────
_THIS_DIR = str(Path(__file__).resolve().parent)
Z2M_BRIDGE_SRC = str(Path(__file__).resolve().parent.parent / "src")

if Z2M_BRIDGE_SRC not in sys.path:
    sys.path.insert(0, Z2M_BRIDGE_SRC)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# ── Environment defaults (set BEFORE importing source modules) ──
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("MQTT_PORT", "1883")
os.environ.setdefault("MQTT_USER", "test_user")
os.environ.setdefault("MQTT_PASS", "test_pass")


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def mock_mqtt():
    """Create a mock MQTTBridge instance."""
    mqtt = MagicMock()
    mqtt.publish = MagicMock()
    mqtt.publish_z2m_set = MagicMock()
    mqtt.register_device = MagicMock()
    mqtt.register_z2m_device = MagicMock()
    mqtt.connect = MagicMock()
    mqtt.stop = MagicMock()
    return mqtt


@pytest.fixture
def sample_config():
    """Return a sample zigbee2mqtt-bridge configuration dict."""
    return {
        "z2m_base_topic": "zigbee2mqtt",
        "devices": [
            {
                "type": "temp_humidity",
                "z2m_friendly_name": "living_room_sensor",
                "soms_device_id": "z2m_temp_01",
                "zone": "main",
                "label": "温湿度センサー",
            },
            {
                "type": "motion",
                "z2m_friendly_name": "entrance_motion",
                "soms_device_id": "z2m_motion_01",
                "zone": "entrance",
                "label": "Entrance Motion",
            },
            {
                "type": "contact",
                "z2m_friendly_name": "door_sensor",
                "soms_device_id": "z2m_door_01",
                "zone": "entrance",
                "label": "Door Sensor",
            },
            {
                "type": "plug",
                "z2m_friendly_name": "desk_plug",
                "soms_device_id": "z2m_plug_01",
                "zone": "main",
                "label": "Desk Plug",
            },
            {
                "type": "light",
                "z2m_friendly_name": "ceiling_light",
                "soms_device_id": "z2m_light_01",
                "zone": "main",
                "label": "Ceiling Light",
            },
        ],
    }


@pytest.fixture
def sample_yaml_content():
    """Return sample YAML text with env var placeholders."""
    return """\
z2m_base_topic: zigbee2mqtt
devices:
  - type: temp_humidity
    z2m_friendly_name: living_room_sensor
    soms_device_id: z2m_temp_01
    zone: main
    label: "温湿度センサー"
"""


# ── Z2M Payload Fixtures ───────────────────────────────────────

@pytest.fixture
def z2m_temp_humidity_payload():
    """Sample Z2M temperature/humidity sensor payload."""
    return {
        "temperature": 23.5,
        "humidity": 55,
        "pressure": 1013.2,
        "battery": 87,
        "linkquality": 120,
    }


@pytest.fixture
def z2m_motion_payload():
    """Sample Z2M motion sensor payload."""
    return {
        "occupancy": True,
        "illuminance": 450,
        "illuminance_lux": 450,
        "battery": 95,
        "linkquality": 80,
    }


@pytest.fixture
def z2m_presence_payload():
    """Sample Z2M 24GHz presence sensor payload."""
    return {
        "presence": True,
        "battery": 100,
        "fading_time": 7579,
        "indicator": "OFF",
        "motion_detection_sensitivity": 8,
        "static_detection_distance": 5,
        "static_detection_sensitivity": 6,
        "linkquality": 160,
    }


@pytest.fixture
def z2m_illuminance_payload():
    """Sample Z2M illuminance sensor payload."""
    return {
        "illuminance": 190,
        "battery": 100,
        "voltage": 3000,
        "linkquality": 251,
    }


@pytest.fixture
def z2m_contact_payload():
    """Sample Z2M contact sensor payload."""
    return {
        "contact": False,  # open
        "battery": 100,
        "linkquality": 150,
    }


@pytest.fixture
def z2m_plug_payload():
    """Sample Z2M smart plug payload."""
    return {
        "state": "ON",
        "power": 45.2,
        "voltage": 121.5,
        "current": 0.37,
        "energy": 12.5,
    }


@pytest.fixture
def z2m_light_payload():
    """Sample Z2M smart light payload."""
    return {
        "state": "ON",
        "brightness": 200,
        "color_temp": 370,
    }


@pytest.fixture
def z2m_availability_online():
    """Z2M availability payload for online device."""
    return {"state": "online"}


@pytest.fixture
def z2m_availability_offline():
    """Z2M availability payload for offline device."""
    return {"state": "offline"}
