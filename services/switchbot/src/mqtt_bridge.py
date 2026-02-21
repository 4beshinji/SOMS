"""MQTT connection and message routing for SwitchBot bridge."""

import json
import logging
import os
import time

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTBridge:
    """Manages MQTT connection and dispatches MCP requests to devices."""

    def __init__(self):
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._devices: dict = {}  # soms_device_id -> device instance
        self._connected = False

        broker = os.getenv("MQTT_BROKER", "mosquitto")
        port = int(os.getenv("MQTT_PORT", "1883"))
        user = os.getenv("MQTT_USER")
        passwd = os.getenv("MQTT_PASS")

        if user:
            self._client.username_pw_set(user, passwd)

        self._broker = broker
        self._port = port
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def register_device(self, device):
        """Register a device for MCP routing."""
        self._devices[device.soms_device_id] = device

    def connect(self):
        """Connect to MQTT broker with retry."""
        while True:
            try:
                self._client.connect(self._broker, self._port, 60)
                break
            except Exception:
                logger.warning("Waiting for MQTT broker...")
                time.sleep(2)
        self._client.loop_start()
        logger.info(f"MQTT loop started (broker={self._broker}:{self._port})")

    def publish(self, topic: str, payload: dict):
        """Publish JSON payload to topic."""
        self._client.publish(topic, json.dumps(payload))

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._connected = True
            logger.info("Connected to MQTT broker")
            for device in self._devices.values():
                topic = f"mcp/{device.soms_device_id}/request/call_tool"
                client.subscribe(topic)
                logger.info(f"Subscribed: {topic}")
        else:
            logger.error(f"MQTT connection failed: rc={rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic
            # Route to matching device
            for dev_id, device in self._devices.items():
                if topic == f"mcp/{dev_id}/request/call_tool":
                    device.handle_mcp_request(payload)
                    return
        except Exception as e:
            logger.error(f"MQTT message error: {e}")

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()
