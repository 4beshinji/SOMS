"""Unit tests for mqtt_bridge.py — topic routing, Z2M message handling, MCP dispatch."""
import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from mqtt_bridge import MQTTBridge


# ── Helper ────────────────────────────────────────────────────

def make_mqtt_msg(topic: str, payload: dict | list | str) -> MagicMock:
    """Create a mock MQTT message."""
    msg = MagicMock()
    msg.topic = topic
    if isinstance(payload, (dict, list)):
        msg.payload = json.dumps(payload).encode()
    else:
        msg.payload = payload.encode() if isinstance(payload, str) else payload
    return msg


# ── MQTTBridge init tests ────────────────────────────────────

class TestMQTTBridgeInit:

    @patch("mqtt_bridge.mqtt.Client")
    def test_default_z2m_base_topic(self, mock_client_cls):
        bridge = MQTTBridge()
        assert bridge._z2m_base_topic == "zigbee2mqtt"

    @patch("mqtt_bridge.mqtt.Client")
    def test_custom_z2m_base_topic(self, mock_client_cls):
        bridge = MQTTBridge(z2m_base_topic="my_z2m")
        assert bridge._z2m_base_topic == "my_z2m"


# ── Z2M message routing tests ────────────────────────────────

class TestZ2MMessageRouting:

    @patch("mqtt_bridge.mqtt.Client")
    def test_routes_state_to_device(self, mock_client_cls):
        bridge = MQTTBridge()
        device = MagicMock()
        device.soms_device_id = "z2m_temp_01"
        device.z2m_friendly_name = "living_room_sensor"

        bridge.register_z2m_device("living_room_sensor", device)

        msg = make_mqtt_msg("zigbee2mqtt/living_room_sensor", {"temperature": 23.5})
        bridge._on_message(None, None, msg)

        device.handle_z2m_state.assert_called_once_with({"temperature": 23.5})

    @patch("mqtt_bridge.mqtt.Client")
    def test_routes_availability_to_device(self, mock_client_cls):
        bridge = MQTTBridge()
        device = MagicMock()
        bridge.register_z2m_device("sensor_01", device)

        msg = make_mqtt_msg("zigbee2mqtt/sensor_01/availability", {"state": "online"})
        bridge._on_message(None, None, msg)

        device.handle_z2m_availability.assert_called_once_with({"state": "online"})

    @patch("mqtt_bridge.mqtt.Client")
    def test_ignores_bridge_messages(self, mock_client_cls):
        bridge = MQTTBridge()
        device = MagicMock()
        bridge.register_z2m_device("anything", device)

        msg = make_mqtt_msg("zigbee2mqtt/bridge/state", {"state": "online"})
        bridge._on_message(None, None, msg)

        device.handle_z2m_state.assert_not_called()
        device.handle_z2m_availability.assert_not_called()

    @patch("mqtt_bridge.mqtt.Client")
    def test_ignores_unknown_device(self, mock_client_cls):
        bridge = MQTTBridge()
        # No devices registered

        msg = make_mqtt_msg("zigbee2mqtt/unknown_device", {"temperature": 20})
        # Should not raise
        bridge._on_message(None, None, msg)

    @patch("mqtt_bridge.mqtt.Client")
    def test_ignores_invalid_json(self, mock_client_cls):
        bridge = MQTTBridge()
        device = MagicMock()
        bridge.register_z2m_device("sensor", device)

        msg = MagicMock()
        msg.topic = "zigbee2mqtt/sensor"
        msg.payload = b"not json {"
        # Should not raise
        bridge._on_message(None, None, msg)
        device.handle_z2m_state.assert_not_called()


# ── MCP routing tests ────────────────────────────────────────

class TestMCPRouting:

    @patch("mqtt_bridge.mqtt.Client")
    def test_routes_mcp_to_device(self, mock_client_cls):
        bridge = MQTTBridge()
        device = MagicMock()
        device.soms_device_id = "z2m_plug_01"
        bridge.register_device(device)

        request = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {"name": "turn_on", "arguments": {}},
            "id": "req-001",
        }
        msg = make_mqtt_msg("mcp/z2m_plug_01/request/call_tool", request)
        bridge._on_message(None, None, msg)

        device.handle_mcp_request.assert_called_once_with(request)

    @patch("mqtt_bridge.mqtt.Client")
    def test_mcp_ignores_unknown_device(self, mock_client_cls):
        bridge = MQTTBridge()
        # No devices registered

        request = {"jsonrpc": "2.0", "method": "call_tool", "params": {}, "id": "x"}
        msg = make_mqtt_msg("mcp/unknown/request/call_tool", request)
        # Should not raise
        bridge._on_message(None, None, msg)


# ── publish_z2m_set tests ────────────────────────────────────

class TestPublishZ2MSet:

    @patch("mqtt_bridge.mqtt.Client")
    def test_publish_z2m_set_correct_topic(self, mock_client_cls):
        bridge = MQTTBridge()
        mock_client = mock_client_cls.return_value

        bridge.publish_z2m_set("desk_plug", {"state": "ON"})

        mock_client.publish.assert_called_once_with(
            "zigbee2mqtt/desk_plug/set",
            json.dumps({"state": "ON"}),
        )

    @patch("mqtt_bridge.mqtt.Client")
    def test_publish_z2m_set_custom_base_topic(self, mock_client_cls):
        bridge = MQTTBridge(z2m_base_topic="my_z2m")
        mock_client = mock_client_cls.return_value

        bridge.publish_z2m_set("light_01", {"brightness": 200})

        mock_client.publish.assert_called_once_with(
            "my_z2m/light_01/set",
            json.dumps({"brightness": 200}),
        )


# ── on_connect tests ─────────────────────────────────────────

class TestOnConnect:

    @patch("mqtt_bridge.mqtt.Client")
    def test_subscribes_to_z2m_wildcard(self, mock_client_cls):
        bridge = MQTTBridge()
        mock_client = mock_client_cls.return_value

        bridge._on_connect(mock_client, None, None, 0)

        # Should subscribe to zigbee2mqtt/#
        subscribe_calls = mock_client.subscribe.call_args_list
        topics = [c[0][0] for c in subscribe_calls]
        assert "zigbee2mqtt/#" in topics

    @patch("mqtt_bridge.mqtt.Client")
    def test_subscribes_to_mcp_per_device(self, mock_client_cls):
        bridge = MQTTBridge()
        mock_client = mock_client_cls.return_value

        device = MagicMock()
        device.soms_device_id = "z2m_plug_01"
        bridge.register_device(device)

        bridge._on_connect(mock_client, None, None, 0)

        subscribe_calls = mock_client.subscribe.call_args_list
        topics = [c[0][0] for c in subscribe_calls]
        assert "mcp/z2m_plug_01/request/call_tool" in topics

    @patch("mqtt_bridge.mqtt.Client")
    def test_connection_failure_logged(self, mock_client_cls):
        bridge = MQTTBridge()
        mock_client = mock_client_cls.return_value

        # rc != 0 means failure
        bridge._on_connect(mock_client, None, None, 5)
        assert bridge._connected is False


# ── bridge/devices auto-discovery tests ──────────────────────

class TestBridgeDevicesDiscovery:

    @patch("mqtt_bridge.mqtt.Client")
    def test_bridge_devices_no_longer_skipped(self, mock_client_cls):
        """bridge/devices messages are processed (not skipped like other bridge/* topics)."""
        bridge = MQTTBridge()
        # The _on_bridge_devices callback should be set
        assert hasattr(bridge, '_on_bridge_devices')

    @patch("mqtt_bridge.mqtt.Client")
    def test_bridge_devices_stores_list(self, mock_client_cls):
        bridge = MQTTBridge()
        devices_payload = [
            {"friendly_name": "0xaaa", "ieee_address": "0xaaa",
             "definition": {"model": "TS0601", "description": "Presence sensor", "vendor": "Tuya"},
             "supported": True, "type": "EndDevice"},
            {"friendly_name": "Coordinator", "ieee_address": "0x00",
             "type": "Coordinator"},
        ]
        msg = make_mqtt_msg("zigbee2mqtt/bridge/devices", devices_payload)
        bridge._on_message(None, None, msg)
        # Should store non-Coordinator devices
        assert len(bridge.z2m_devices_list) == 1
        assert bridge.z2m_devices_list[0]["friendly_name"] == "0xaaa"

    @patch("mqtt_bridge.mqtt.Client")
    def test_bridge_devices_updates_on_new_message(self, mock_client_cls):
        bridge = MQTTBridge()
        msg1 = make_mqtt_msg("zigbee2mqtt/bridge/devices", [
            {"friendly_name": "a", "ieee_address": "0xa", "type": "EndDevice"},
        ])
        bridge._on_message(None, None, msg1)
        assert len(bridge.z2m_devices_list) == 1

        msg2 = make_mqtt_msg("zigbee2mqtt/bridge/devices", [
            {"friendly_name": "a", "ieee_address": "0xa", "type": "EndDevice"},
            {"friendly_name": "b", "ieee_address": "0xb", "type": "EndDevice"},
        ])
        bridge._on_message(None, None, msg2)
        assert len(bridge.z2m_devices_list) == 2

    @patch("mqtt_bridge.mqtt.Client")
    def test_bridge_state_still_ignored(self, mock_client_cls):
        """Other bridge/* topics (state, log, etc.) still ignored."""
        bridge = MQTTBridge()
        device = MagicMock()
        bridge.register_z2m_device("anything", device)
        msg = make_mqtt_msg("zigbee2mqtt/bridge/state", {"state": "online"})
        bridge._on_message(None, None, msg)
        device.handle_z2m_state.assert_not_called()
