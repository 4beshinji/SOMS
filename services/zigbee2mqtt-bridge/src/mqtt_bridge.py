"""MQTT bridge: subscribes to Z2M topics, publishes SOMS telemetry, handles MCP."""

import json
import logging
import os
import time

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTBridge:
    """Single MQTT client that handles Z2M subscription, SOMS telemetry, and MCP routing."""

    def __init__(self, z2m_base_topic: str = "zigbee2mqtt"):
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._z2m_base_topic = z2m_base_topic
        self._devices: dict = {}  # soms_device_id -> device instance
        self._z2m_name_map: dict = {}  # z2m_friendly_name -> device instance
        self._connected = False
        self.z2m_devices_list: list[dict] = []  # latest bridge/devices payload (non-Coordinator)
        self._on_bridge_devices = None  # callback(list[dict]) for auto-registration

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

    def register_z2m_device(self, friendly_name: str, device):
        """Register friendly_name → device mapping for Z2M message routing."""
        self._z2m_name_map[friendly_name] = device

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

    def publish_z2m_set(self, friendly_name: str, payload: dict):
        """Publish a set command to Z2M for a specific device."""
        topic = f"{self._z2m_base_topic}/{friendly_name}/set"
        self._client.publish(topic, json.dumps(payload))
        logger.info(f"Z2M set: {topic} <- {payload}")

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._connected = True
            logger.info("Connected to MQTT broker")

            # Subscribe to Z2M topics
            z2m_topic = f"{self._z2m_base_topic}/#"
            client.subscribe(z2m_topic)
            logger.info(f"Subscribed: {z2m_topic}")

            # Subscribe to MCP request topics for each device
            for device in self._devices.values():
                topic = f"mcp/{device.soms_device_id}/request/call_tool"
                client.subscribe(topic)
                logger.info(f"Subscribed: {topic}")
        else:
            logger.error(f"MQTT connection failed: rc={rc}")

    def _on_message(self, client, userdata, msg):
        try:
            topic = msg.topic

            # Route MCP requests
            if topic.startswith("mcp/"):
                payload = json.loads(msg.payload.decode())
                for dev_id, device in self._devices.items():
                    if topic == f"mcp/{dev_id}/request/call_tool":
                        device.handle_mcp_request(payload)
                        return
                return

            # Route Z2M messages
            if topic.startswith(self._z2m_base_topic + "/"):
                self._handle_z2m_message(topic, msg.payload)

        except Exception as e:
            logger.error(f"MQTT message error: {e}")

    def _handle_z2m_message(self, topic: str, raw_payload: bytes):
        """Route Z2M topic to appropriate device handler."""
        # Strip base topic prefix
        suffix = topic[len(self._z2m_base_topic) + 1:]

        # Handle bridge/devices (Z2M publishes full device list as retained)
        if suffix == "bridge/devices":
            try:
                payload = json.loads(raw_payload.decode())
                if isinstance(payload, list):
                    self.z2m_devices_list = [
                        d for d in payload if d.get("type") != "Coordinator"
                    ]
                    logger.info(
                        "Received Z2M device list: %d devices (excl. Coordinator)",
                        len(self.z2m_devices_list),
                    )
                    if self._on_bridge_devices:
                        self._on_bridge_devices(self.z2m_devices_list)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
            return

        # Skip other bridge messages (bridge/state, bridge/log, etc.)
        if suffix.startswith("bridge/"):
            return

        # Parse payload
        try:
            payload = json.loads(raw_payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        # Check for availability messages: zigbee2mqtt/{name}/availability
        if suffix.endswith("/availability"):
            friendly_name = suffix[: -len("/availability")]
            device = self._z2m_name_map.get(friendly_name)
            if device:
                device.handle_z2m_availability(payload)
            return

        # State updates: zigbee2mqtt/{name} (no sub-path)
        # Only match exact friendly names (no slashes in the remaining suffix)
        if "/" not in suffix:
            friendly_name = suffix
            device = self._z2m_name_map.get(friendly_name)
            if device and isinstance(payload, dict):
                device.handle_z2m_state(payload)

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()
