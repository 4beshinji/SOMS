"""MQTT client for publishing anomaly detections and subscribing to sensor data."""
import json
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from loguru import logger

from config import settings
from scorer import AnomalyResult


class AnomalyMQTTClient:
    TOPIC_PREFIX = "office"

    def __init__(self, on_sensor_message=None):
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="soms-anomaly"
        )
        self._client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASS)
        self._connected = False
        self._on_sensor_message = on_sensor_message

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        if on_sensor_message:
            self._client.on_message = self._on_message

    def connect(self):
        """Connect to MQTT broker."""
        try:
            self._client.connect(settings.MQTT_BROKER, settings.MQTT_PORT)
            self._client.loop_start()
            logger.info(
                "MQTT connecting to {}:{}", settings.MQTT_BROKER, settings.MQTT_PORT
            )
        except Exception as e:
            logger.error("MQTT connection failed: {}", e)

    def disconnect(self):
        """Disconnect from MQTT broker."""
        self._client.loop_stop()
        self._client.disconnect()
        self._connected = False

    def publish_anomaly(self, result: AnomalyResult):
        """Publish anomaly detection to MQTT.

        Topic: office/{zone}/anomaly/{channel}
        """
        topic = f"{self.TOPIC_PREFIX}/{result.zone}/anomaly/{result.channel}"
        payload = {
            "score": result.score,
            "predicted": result.predicted,
            "actual": result.actual,
            "threshold": result.score,  # the score itself exceeded threshold
            "severity": result.severity,
            "source": result.source,
            "channel": result.channel,
            "zone": result.zone,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._client.publish(topic, json.dumps(payload), qos=1)
        logger.info(
            "Published anomaly: {} {} score={} severity={}",
            result.zone,
            result.channel,
            result.score,
            result.severity,
        )

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._connected = True
            logger.info("MQTT connected")
            if self._on_sensor_message:
                # Subscribe to all sensor readings for realtime detection
                client.subscribe("office/+/sensor/+/+", qos=0)
                logger.info("Subscribed to office/+/sensor/+/+")
        else:
            logger.error("MQTT connect failed with rc={}", rc)

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        self._connected = False
        if rc != 0:
            logger.warning("MQTT disconnected unexpectedly (rc={})", rc)

    def _on_message(self, client, userdata, msg):
        """Route incoming sensor messages to the callback."""
        try:
            parts = msg.topic.split("/")
            if len(parts) < 5 or parts[2] != "sensor":
                return
            zone = parts[1]
            channel = parts[4]
            payload = json.loads(msg.payload.decode())
            value = payload.get("value")
            if value is not None and self._on_sensor_message:
                self._on_sensor_message(zone, channel, float(value))
        except Exception as e:
            logger.debug("Failed to parse MQTT message: {}", e)

    @property
    def connected(self) -> bool:
        return self._connected
