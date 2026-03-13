"""Configuration loader for wifi-pose service."""
from __future__ import annotations

import os
from pathlib import Path

import yaml


def load_config(config_path: str | None = None) -> dict:
    """Load configuration from YAML file with env var overrides."""
    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "config" / "wifi_pose.yaml")

    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    # Environment variable overrides
    mqtt = config.setdefault("mqtt", {})
    mqtt["broker"] = os.getenv("MQTT_BROKER", mqtt.get("broker", "localhost"))
    mqtt["port"] = int(os.getenv("MQTT_PORT", mqtt.get("port", 1883)))

    return config
