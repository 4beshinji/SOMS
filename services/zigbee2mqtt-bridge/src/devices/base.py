"""Abstract base class for Zigbee2MQTT device wrappers."""

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class ZigbeeDevice(ABC):
    """Base class for all Zigbee2MQTT device types.

    Each subclass maps Z2M state payloads to SOMS
    MQTT telemetry (per-channel {"value": X}) and MCP tool calls.
    Unlike SwitchBot devices, Z2M pushes state — no polling needed.
    """

    device_type: str = "unknown"
    BATTERY_LOW_THRESHOLD: int = 20

    # Subclasses override to define per-channel aggregation.
    #   "count"  — count truthy events, publish as {channel}_count on flush
    #   "latest" — hold last value, always publish on flush (even if unchanged)
    # Channels not listed here are published immediately (passthrough).
    channel_aggregation: dict[str, str] = {}

    def __init__(self, z2m_friendly_name: str, soms_device_id: str, zone: str,
                 label: str, mqtt_bridge):
        self.z2m_friendly_name = z2m_friendly_name
        self.soms_device_id = soms_device_id
        self.zone = zone
        self.label = label
        self._mqtt = mqtt_bridge
        self._tools: dict[str, Any] = {}
        self._last_state: dict = {}
        self._online: bool = False
        self._battery: int | None = None
        self._battery_low_alerted: bool = False
        self._channel_buffer: dict[str, Any] = {}

        # Always register get_status
        self.register_tool("get_status", self._tool_get_status)

    @property
    def topic_prefix(self) -> str:
        return f"office/{self.zone}/sensor/{self.soms_device_id}"

    @property
    def is_actuator(self) -> bool:
        """Actuator devices can receive set commands."""
        return self.device_type in ("plug", "light")

    def register_tool(self, name: str, callback):
        self._tools[name] = callback

    # --- Telemetry ---

    def publish_channel(self, channel: str, value):
        """Publish a single channel: office/{zone}/sensor/{id}/{channel} -> {"value": X}"""
        topic = f"{self.topic_prefix}/{channel}"
        self._mqtt.publish(topic, {"value": value})

    def publish_channels(self, data: dict):
        """Publish or buffer channels based on aggregation mode."""
        for channel, value in data.items():
            mode = self.channel_aggregation.get(channel)
            if mode == "count":
                if value:  # only count truthy events (e.g. motion=1)
                    self._channel_buffer[channel] = (
                        self._channel_buffer.get(channel, 0) + 1
                    )
            elif mode == "latest":
                self._channel_buffer[channel] = value
            else:
                self.publish_channel(channel, value)

    def flush_channels(self):
        """Publish aggregated channels and reset counters.

        Called periodically by DeviceManager (default every 30s).
        - count: publish {channel}_count with accumulated count, then reset to 0
        - latest: publish held value (even if unchanged)
        """
        for channel, value in list(self._channel_buffer.items()):
            mode = self.channel_aggregation.get(channel)
            if mode == "count":
                self.publish_channel(f"{channel}_count", value)
                self._channel_buffer[channel] = 0
            elif mode == "latest":
                self.publish_channel(channel, value)

    def publish_heartbeat(self):
        """Publish heartbeat for DeviceRegistry recognition."""
        payload = {
            "device_id": self.soms_device_id,
            "device_type": self.device_type,
            "zone": self.zone,
            "label": self.label,
            "source": "zigbee2mqtt_bridge",
            "z2m_friendly_name": self.z2m_friendly_name,
            "online": self._online,
            "battery": self._battery,
            "timestamp": int(time.time()),
        }
        self._mqtt.publish(f"{self.topic_prefix}/heartbeat", payload)

    # --- Z2M State Handling ---

    def handle_z2m_state(self, payload: dict):
        """Process incoming Z2M state payload and publish SOMS telemetry.

        Battery is extracted here (not in state_to_channels) to keep
        diagnostic data out of WorldModel/LLM context. Battery level
        is included in heartbeat payloads instead. A battery_low alert
        is published only when battery drops below the threshold.
        """
        self._last_state = payload

        # Extract battery — diagnostic only, not telemetry
        if "battery" in payload:
            self._battery = payload["battery"]
            self._check_battery_low()

        channels = self.state_to_channels(payload)
        if channels:
            self.publish_channels(channels)

    def _check_battery_low(self):
        """Publish battery_low alert only on threshold crossing."""
        if self._battery is None:
            return
        is_low = self._battery <= self.BATTERY_LOW_THRESHOLD
        if is_low and not self._battery_low_alerted:
            self._battery_low_alerted = True
            self.publish_channel("battery_low", self._battery)
            logger.warning(
                f"[{self.soms_device_id}] Battery low: {self._battery}%"
            )
        elif not is_low and self._battery_low_alerted:
            # Reset alert when battery recovers (e.g. replaced)
            self._battery_low_alerted = False

    def handle_z2m_availability(self, payload: dict):
        """Process Z2M availability message (online/offline)."""
        if isinstance(payload, dict):
            state = payload.get("state", "offline")
        else:
            state = str(payload)
        self._online = state == "online"
        logger.info(f"[{self.soms_device_id}] availability: {state}")

    @abstractmethod
    def state_to_channels(self, state: dict) -> dict:
        """Convert Z2M state dict to {channel: value} for SOMS telemetry.

        Subclasses must implement this to map device-specific fields.
        """

    # --- Actuator Control ---

    def _publish_z2m_set(self, payload: dict):
        """Publish a set command to Z2M for this device."""
        self._mqtt.publish_z2m_set(self.z2m_friendly_name, payload)

    # --- MCP ---

    def handle_mcp_request(self, payload: dict):
        """Handle incoming MCP JSON-RPC 2.0 tool call."""
        req_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if method != "call_tool" or tool_name not in self._tools:
            error_resp = {
                "jsonrpc": "2.0",
                "error": f"Unknown tool: {tool_name}",
                "id": req_id,
            }
            self._mqtt.publish(f"mcp/{self.soms_device_id}/response/{req_id}", error_resp)
            return

        logger.info(f"[{self.soms_device_id}] MCP call: {tool_name}({args})")
        try:
            result = self._tools[tool_name](**args)
            response = {"jsonrpc": "2.0", "result": result, "id": req_id}
        except Exception as e:
            logger.error(f"[{self.soms_device_id}] Tool error: {e}")
            response = {"jsonrpc": "2.0", "error": str(e), "id": req_id}

        self._mqtt.publish(f"mcp/{self.soms_device_id}/response/{req_id}", response)

    def _tool_get_status(self):
        """Return cached state."""
        return dict(self._last_state)
