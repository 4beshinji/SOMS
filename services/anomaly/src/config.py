"""Configuration for the anomaly detection service."""
import os

import yaml
from loguru import logger


class AnomalySettings:
    DATABASE_URL: str
    MQTT_BROKER: str
    MQTT_PORT: int
    MQTT_USER: str
    MQTT_PASS: str
    MODEL_ARCH: str
    WINDOW_SIZE: int
    HORIZON: int
    INFERENCE_INTERVAL: int
    REALTIME_ENABLED: bool
    REALTIME_BUFFER_MIN: int
    WARNING_THRESHOLD: float
    CRITICAL_THRESHOLD: float
    MODEL_STORE_PATH: str
    RETRAIN_DAY: int
    RETRAIN_HOUR_UTC: int
    MIN_DATA_DAYS: int

    def __init__(self):
        self.DATABASE_URL = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://soms:soms_dev_password@localhost:5432/soms",
        )
        self.MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
        self.MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
        self.MQTT_USER = os.getenv("MQTT_USER", "soms")
        self.MQTT_PASS = os.getenv("MQTT_PASS", "soms_dev_mqtt")
        self.MODEL_ARCH = "auto"
        self.WINDOW_SIZE = 168
        self.HORIZON = 6
        self.INFERENCE_INTERVAL = 600
        self.REALTIME_ENABLED = True
        self.REALTIME_BUFFER_MIN = 60
        self.WARNING_THRESHOLD = 3.0
        self.CRITICAL_THRESHOLD = 5.0
        self.MODEL_STORE_PATH = os.getenv("MODEL_STORE_PATH", "/app/model_store")
        self.RETRAIN_DAY = 6  # Sunday
        self.RETRAIN_HOUR_UTC = 3
        self.MIN_DATA_DAYS = 30

        self._load_yaml()

    def _load_yaml(self):
        """Override defaults from config/anomaly.yaml if present."""
        for path in ["config/anomaly.yaml", "/app/config/anomaly.yaml"]:
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        cfg = yaml.safe_load(f) or {}
                    for key, value in cfg.items():
                        attr = key.upper()
                        if hasattr(self, attr):
                            setattr(self, attr, type(getattr(self, attr))(value))
                    logger.info("Loaded config from {}", path)
                except Exception as e:
                    logger.warning("Failed to load {}: {}", path, e)
                break


settings = AnomalySettings()
