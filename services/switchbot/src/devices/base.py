"""Abstract base class for SwitchBot device wrappers."""

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class SwitchBotDevice(ABC):
    """Base class for all SwitchBot device types.

    Each subclass maps SwitchBot Cloud API status/commands to SOMS
    MQTT telemetry (per-channel {"value": X}) and MCP tool calls.
    """

    # Subclasses override this with their device type string
    device_type: str = "unknown"

    def __init__(self, switchbot_id: str, soms_device_id: str, zone: str,
                 label: str, api, mqtt_bridge):
        self.switchbot_id = switchbot_id
        self.soms_device_id = soms_device_id
        self.zone = zone
        self.label = label
        self._api = api
        self._mqtt = mqtt_bridge
        self._tools: dict[str, Any] = {}
        self._last_status: dict = {}
        self._last_poll: float = 0

        # Always register get_status
        self.register_tool("get_status", self._tool_get_status)

    @property
    def topic_prefix(self) -> str:
        return f"office/{self.zone}/sensor/{self.soms_device_id}"

    @property
    def is_sensor(self) -> bool:
        """Sensor devices poll more frequently."""
        return self.device_type in ("meter", "motion_sensor", "contact_sensor")

    def register_tool(self, name: str, callback):
        self._tools[name] = callback

    # --- Telemetry ---

    def publish_channel(self, channel: str, value):
        """Publish a single channel: office/{zone}/sensor/{id}/{channel} -> {"value": X}"""
        topic = f"{self.topic_prefix}/{channel}"
        self._mqtt.publish(topic, {"value": value})

    def publish_channels(self, data: dict):
        """Publish multiple channels at once."""
        for channel, value in data.items():
            self.publish_channel(channel, value)

    def publish_heartbeat(self):
        """Publish heartbeat for DeviceRegistry recognition."""
        payload = {
            "device_id": self.soms_device_id,
            "device_type": self.device_type,
            "zone": self.zone,
            "label": self.label,
            "source": "switchbot_bridge",
            "switchbot_id": self.switchbot_id,
            "timestamp": int(time.time()),
        }
        self._mqtt.publish(f"{self.topic_prefix}/heartbeat", payload)

    # --- Polling ---

    async def poll_status(self) -> dict:
        """Fetch status from SwitchBot Cloud and publish telemetry."""
        try:
            status = await self._api.get_device_status(self.switchbot_id)
            self._last_status = status
            self._last_poll = time.time()
            channels = self.status_to_channels(status)
            if channels:
                self.publish_channels(channels)
            return status
        except Exception as e:
            logger.error(f"[{self.soms_device_id}] Poll failed: {e}")
            return {}

    @abstractmethod
    def status_to_channels(self, status: dict) -> dict:
        """Convert SwitchBot API status dict to {channel: value} for telemetry.

        Subclasses must implement this to map device-specific fields.
        """

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
            # If the tool returns a coroutine, we can't await it here
            # (MCP handler is sync from MQTT callback), so we log a warning
            if hasattr(result, "__await__"):
                import asyncio
                loop = asyncio.get_event_loop()
                result = loop.run_until_complete(result) if not loop.is_running() else {"status": "queued"}

            response = {"jsonrpc": "2.0", "result": result, "id": req_id}
        except Exception as e:
            logger.error(f"[{self.soms_device_id}] Tool error: {e}")
            response = {"jsonrpc": "2.0", "error": str(e), "id": req_id}

        self._mqtt.publish(f"mcp/{self.soms_device_id}/response/{req_id}", response)

    def _tool_get_status(self):
        """Return cached status."""
        return dict(self._last_status)
