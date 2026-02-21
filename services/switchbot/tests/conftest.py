"""Shared fixtures and helpers for SwitchBot Bridge unit tests."""
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Path setup ──────────────────────────────────────────────────
_THIS_DIR = str(Path(__file__).resolve().parent)
SWITCHBOT_SRC = str(Path(__file__).resolve().parent.parent / "src")

if SWITCHBOT_SRC not in sys.path:
    sys.path.insert(0, SWITCHBOT_SRC)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# ── Environment defaults (set BEFORE importing source modules) ──
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("MQTT_PORT", "1883")
os.environ.setdefault("MQTT_USER", "test_user")
os.environ.setdefault("MQTT_PASS", "test_pass")
os.environ.setdefault("SWITCHBOT_TOKEN", "test_token")
os.environ.setdefault("SWITCHBOT_SECRET", "test_secret")


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def mock_api():
    """Create a mock SwitchBotAPI instance."""
    api = AsyncMock()
    api.get_device_status = AsyncMock(return_value={
        "temperature": 22.5,
        "humidity": 55,
        "battery": 90,
    })
    api.get_devices = AsyncMock(return_value={"deviceList": [], "infraredRemoteList": []})
    api.send_command = AsyncMock(return_value={"status": "ok"})
    api.close = AsyncMock()
    return api


@pytest.fixture
def mock_mqtt():
    """Create a mock MQTTBridge instance."""
    mqtt = MagicMock()
    mqtt.publish = MagicMock()
    mqtt.register_device = MagicMock()
    mqtt.connect = MagicMock()
    mqtt.stop = MagicMock()
    return mqtt


@pytest.fixture
def sample_config():
    """Return a sample switchbot configuration dict."""
    return {
        "api": {
            "token": "test_token_abc",
            "secret": "test_secret_xyz",
        },
        "polling": {
            "sensor_interval_sec": 120,
            "actuator_interval_sec": 300,
            "stagger_delay_ms": 200,
        },
        "devices": [
            {
                "type": "meter",
                "switchbot_id": "AABBCCDDEE01",
                "soms_device_id": "switchbot_meter_01",
                "zone": "main",
                "label": "Office Thermometer",
            },
            {
                "type": "bot",
                "switchbot_id": "AABBCCDDEE02",
                "soms_device_id": "switchbot_bot_01",
                "zone": "main",
                "label": "Light Switch",
            },
            {
                "type": "motion_sensor",
                "switchbot_id": "AABBCCDDEE03",
                "soms_device_id": "switchbot_motion_01",
                "zone": "entrance",
                "label": "Entrance Motion",
            },
        ],
        "webhook": {
            "enabled": False,
            "port": 8005,
        },
    }


@pytest.fixture
def sample_yaml_content():
    """Return sample YAML text with env var placeholders."""
    return """\
api:
  token: "${SWITCHBOT_TOKEN}"
  secret: "${SWITCHBOT_SECRET}"
polling:
  sensor_interval_sec: 120
  actuator_interval_sec: 300
  stagger_delay_ms: 200
devices:
  - type: meter
    switchbot_id: AABBCCDDEE01
    soms_device_id: switchbot_meter_01
    zone: main
    label: "Office Thermometer"
"""
