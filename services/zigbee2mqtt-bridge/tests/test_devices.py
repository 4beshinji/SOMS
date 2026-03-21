"""Unit tests for device implementations — state_to_channels, MCP tools, heartbeat."""
import json
import time
from unittest.mock import MagicMock, call

import pytest

from devices.base import ZigbeeDevice
from devices.temp_humidity import TempHumidityDevice
from devices.motion import MotionDevice
from devices.presence import PresenceDevice
from devices.illuminance import IlluminanceDevice
from devices.contact import ContactDevice
from devices.plug import PlugDevice
from devices.light import LightDevice


# ── Helper ────────────────────────────────────────────────────

def make_device(cls, mock_mqtt, **kwargs):
    """Create a device instance with default test parameters."""
    defaults = {
        "z2m_friendly_name": "test_device",
        "soms_device_id": "z2m_test_01",
        "zone": "main",
        "label": "Test Device",
        "mqtt_bridge": mock_mqtt,
    }
    defaults.update(kwargs)
    return cls(**defaults)


# ── TempHumidityDevice tests ──────────────────────────────────

class TestTempHumidityDevice:

    def test_device_type(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        assert dev.device_type == "temp_humidity"

    def test_state_to_channels_full(self, mock_mqtt, z2m_temp_humidity_payload):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        channels = dev.state_to_channels(z2m_temp_humidity_payload)
        assert channels["temperature"] == 23.5
        assert channels["humidity"] == 55
        assert channels["pressure"] == 1013.2
        assert "battery" not in channels

    def test_state_to_channels_partial(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        channels = dev.state_to_channels({"temperature": 20.0})
        assert channels == {"temperature": 20.0}

    def test_state_to_channels_empty(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        channels = dev.state_to_channels({"linkquality": 100})
        assert channels == {}

    def test_is_not_actuator(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        assert dev.is_actuator is False


# ── MotionDevice tests ────────────────────────────────────────

class TestMotionDevice:

    def test_device_type(self, mock_mqtt):
        dev = make_device(MotionDevice, mock_mqtt)
        assert dev.device_type == "motion"

    def test_occupancy_true_maps_to_motion_1(self, mock_mqtt):
        dev = make_device(MotionDevice, mock_mqtt)
        channels = dev.state_to_channels({"occupancy": True})
        assert channels["motion"] == 1

    def test_occupancy_false_maps_to_motion_0(self, mock_mqtt):
        dev = make_device(MotionDevice, mock_mqtt)
        channels = dev.state_to_channels({"occupancy": False})
        assert channels["motion"] == 0

    def test_illuminance_lux_preferred(self, mock_mqtt):
        dev = make_device(MotionDevice, mock_mqtt)
        channels = dev.state_to_channels({"illuminance": 100, "illuminance_lux": 450})
        # illuminance_lux overrides illuminance
        assert channels["illuminance"] == 450

    def test_battery_excluded_from_channels(self, mock_mqtt, z2m_motion_payload):
        dev = make_device(MotionDevice, mock_mqtt)
        channels = dev.state_to_channels(z2m_motion_payload)
        assert "battery" not in channels


# ── PresenceDevice tests ──────────────────────────────────────

class TestPresenceDevice:

    def test_device_type(self, mock_mqtt):
        dev = make_device(PresenceDevice, mock_mqtt)
        assert dev.device_type == "presence"

    def test_presence_true_maps_to_motion_1(self, mock_mqtt):
        dev = make_device(PresenceDevice, mock_mqtt)
        channels = dev.state_to_channels({"presence": True})
        assert channels["motion"] == 1

    def test_presence_false_maps_to_motion_0(self, mock_mqtt):
        dev = make_device(PresenceDevice, mock_mqtt)
        channels = dev.state_to_channels({"presence": False})
        assert channels["motion"] == 0

    def test_battery_excluded_from_channels(self, mock_mqtt):
        dev = make_device(PresenceDevice, mock_mqtt)
        channels = dev.state_to_channels({"presence": True, "battery": 100})
        assert "battery" not in channels

    def test_ignores_extra_fields(self, mock_mqtt):
        dev = make_device(PresenceDevice, mock_mqtt)
        channels = dev.state_to_channels({
            "presence": True, "fading_time": 7579,
            "static_detection_sensitivity": 6, "linkquality": 160,
        })
        assert channels == {"motion": 1}

    def test_is_not_actuator(self, mock_mqtt):
        dev = make_device(PresenceDevice, mock_mqtt)
        assert dev.is_actuator is False


# ── IlluminanceDevice tests ───────────────────────────────────

class TestIlluminanceDevice:

    def test_device_type(self, mock_mqtt):
        dev = make_device(IlluminanceDevice, mock_mqtt)
        assert dev.device_type == "illuminance"

    def test_illuminance_value(self, mock_mqtt):
        dev = make_device(IlluminanceDevice, mock_mqtt)
        channels = dev.state_to_channels({"illuminance": 190})
        assert channels["illuminance"] == 190

    def test_illuminance_lux_preferred(self, mock_mqtt):
        dev = make_device(IlluminanceDevice, mock_mqtt)
        channels = dev.state_to_channels({"illuminance": 100, "illuminance_lux": 450})
        assert channels["illuminance"] == 450

    def test_battery_excluded_from_channels(self, mock_mqtt):
        dev = make_device(IlluminanceDevice, mock_mqtt)
        channels = dev.state_to_channels({"illuminance": 190, "battery": 100})
        assert "battery" not in channels

    def test_is_not_actuator(self, mock_mqtt):
        dev = make_device(IlluminanceDevice, mock_mqtt)
        assert dev.is_actuator is False


# ── ContactDevice tests ──────────────────────────────────────

class TestContactDevice:

    def test_device_type(self, mock_mqtt):
        dev = make_device(ContactDevice, mock_mqtt)
        assert dev.device_type == "contact"

    def test_contact_true_means_closed(self, mock_mqtt):
        dev = make_device(ContactDevice, mock_mqtt)
        channels = dev.state_to_channels({"contact": True})
        assert channels["door"] == 0

    def test_contact_false_means_open(self, mock_mqtt):
        dev = make_device(ContactDevice, mock_mqtt)
        channels = dev.state_to_channels({"contact": False})
        assert channels["door"] == 1

    def test_battery_excluded_from_channels(self, mock_mqtt, z2m_contact_payload):
        dev = make_device(ContactDevice, mock_mqtt)
        channels = dev.state_to_channels(z2m_contact_payload)
        assert "battery" not in channels


# ── PlugDevice tests ──────────────────────────────────────────

class TestPlugDevice:

    def test_device_type(self, mock_mqtt):
        dev = make_device(PlugDevice, mock_mqtt)
        assert dev.device_type == "plug"

    def test_is_actuator(self, mock_mqtt):
        dev = make_device(PlugDevice, mock_mqtt)
        assert dev.is_actuator is True

    def test_state_on_maps_to_power_state_1(self, mock_mqtt):
        dev = make_device(PlugDevice, mock_mqtt)
        channels = dev.state_to_channels({"state": "ON"})
        assert channels["power_state"] == 1

    def test_state_off_maps_to_power_state_0(self, mock_mqtt):
        dev = make_device(PlugDevice, mock_mqtt)
        channels = dev.state_to_channels({"state": "OFF"})
        assert channels["power_state"] == 0

    def test_power_and_voltage_channels(self, mock_mqtt, z2m_plug_payload):
        dev = make_device(PlugDevice, mock_mqtt)
        channels = dev.state_to_channels(z2m_plug_payload)
        assert channels["wattage"] == 45.2
        assert channels["voltage"] == 121.5
        assert channels["current"] == 0.37
        assert channels["energy"] == 12.5

    def test_turn_on_publishes_z2m_set(self, mock_mqtt):
        dev = make_device(PlugDevice, mock_mqtt)
        result = dev._turn_on()
        mock_mqtt.publish_z2m_set.assert_called_once_with("test_device", {"state": "ON"})
        assert result["status"] == "ok"

    def test_turn_off_publishes_z2m_set(self, mock_mqtt):
        dev = make_device(PlugDevice, mock_mqtt)
        result = dev._turn_off()
        mock_mqtt.publish_z2m_set.assert_called_once_with("test_device", {"state": "OFF"})
        assert result["status"] == "ok"

    def test_has_turn_on_and_off_tools(self, mock_mqtt):
        dev = make_device(PlugDevice, mock_mqtt)
        assert "turn_on" in dev._tools
        assert "turn_off" in dev._tools
        assert "get_status" in dev._tools


# ── LightDevice tests ────────────────────────────────────────

class TestLightDevice:

    def test_device_type(self, mock_mqtt):
        dev = make_device(LightDevice, mock_mqtt)
        assert dev.device_type == "light"

    def test_is_actuator(self, mock_mqtt):
        dev = make_device(LightDevice, mock_mqtt)
        assert dev.is_actuator is True

    def test_brightness_normalized_to_percent(self, mock_mqtt):
        dev = make_device(LightDevice, mock_mqtt)
        channels = dev.state_to_channels({"brightness": 254})
        assert channels["brightness"] == 100

    def test_brightness_zero(self, mock_mqtt):
        dev = make_device(LightDevice, mock_mqtt)
        channels = dev.state_to_channels({"brightness": 0})
        assert channels["brightness"] == 0

    def test_brightness_mid(self, mock_mqtt):
        dev = make_device(LightDevice, mock_mqtt)
        channels = dev.state_to_channels({"brightness": 127})
        assert channels["brightness"] == 50

    def test_color_temp_passthrough(self, mock_mqtt, z2m_light_payload):
        dev = make_device(LightDevice, mock_mqtt)
        channels = dev.state_to_channels(z2m_light_payload)
        assert channels["color_temp"] == 370

    def test_turn_on_publishes_z2m_set(self, mock_mqtt):
        dev = make_device(LightDevice, mock_mqtt)
        result = dev._turn_on()
        mock_mqtt.publish_z2m_set.assert_called_once_with("test_device", {"state": "ON"})
        assert result["status"] == "ok"

    def test_turn_off_publishes_z2m_set(self, mock_mqtt):
        dev = make_device(LightDevice, mock_mqtt)
        result = dev._turn_off()
        mock_mqtt.publish_z2m_set.assert_called_once_with("test_device", {"state": "OFF"})
        assert result["status"] == "ok"

    def test_set_brightness_converts_to_254_scale(self, mock_mqtt):
        dev = make_device(LightDevice, mock_mqtt)
        result = dev._set_brightness(brightness=50)
        mock_mqtt.publish_z2m_set.assert_called_once_with("test_device", {"brightness": 127})
        assert result["brightness"] == 50

    def test_set_color_temp(self, mock_mqtt):
        dev = make_device(LightDevice, mock_mqtt)
        result = dev._set_color_temp(color_temp=250)
        mock_mqtt.publish_z2m_set.assert_called_once_with("test_device", {"color_temp": 250})
        assert result["color_temp"] == 250

    def test_has_all_tools(self, mock_mqtt):
        dev = make_device(LightDevice, mock_mqtt)
        assert "turn_on" in dev._tools
        assert "turn_off" in dev._tools
        assert "set_brightness" in dev._tools
        assert "set_color_temp" in dev._tools
        assert "get_status" in dev._tools


# ── Base class shared behavior ────────────────────────────────

class TestZigbeeDeviceBase:

    def test_topic_prefix(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt, zone="meeting", soms_device_id="z2m_x")
        assert dev.topic_prefix == "office/meeting/sensor/z2m_x"

    def test_publish_channel(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        dev.publish_channel("temperature", 25.0)
        mock_mqtt.publish.assert_called_once_with(
            "office/main/sensor/z2m_test_01/temperature", {"value": 25.0}
        )

    def test_publish_channels_multiple(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        dev.publish_channels({"temperature": 25.0, "humidity": 50})
        assert mock_mqtt.publish.call_count == 2

    def test_publish_heartbeat(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt,
                          z2m_friendly_name="my_sensor", soms_device_id="z2m_s1")
        dev._online = True
        dev.publish_heartbeat()

        call_args = mock_mqtt.publish.call_args
        topic = call_args[0][0]
        payload = call_args[0][1]

        assert topic == "office/main/sensor/z2m_s1/heartbeat"
        assert payload["device_id"] == "z2m_s1"
        assert payload["source"] == "zigbee2mqtt_bridge"
        assert payload["z2m_friendly_name"] == "my_sensor"
        assert payload["online"] is True

    def test_handle_z2m_state_publishes_channels(self, mock_mqtt, z2m_temp_humidity_payload):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        dev.handle_z2m_state(z2m_temp_humidity_payload)

        # temperature, humidity, pressure only (battery excluded from telemetry)
        assert mock_mqtt.publish.call_count == 3
        assert dev._last_state == z2m_temp_humidity_payload

    def test_handle_z2m_state_extracts_battery(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        dev.handle_z2m_state({"temperature": 22, "battery": 75})
        assert dev._battery == 75

    def test_heartbeat_includes_battery(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt, soms_device_id="z2m_hb")
        dev._battery = 42
        dev.publish_heartbeat()

        payload = mock_mqtt.publish.call_args[0][1]
        assert payload["battery"] == 42

    def test_battery_low_alert_published_on_threshold(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        dev.handle_z2m_state({"temperature": 22, "battery": 19})

        # temperature channel + battery_low alert
        calls = mock_mqtt.publish.call_args_list
        topics = [c[0][0] for c in calls]
        assert "office/main/sensor/z2m_test_01/battery_low" in topics

        # battery_low payload contains the actual battery level
        alert_call = [c for c in calls if "battery_low" in c[0][0]][0]
        assert alert_call[0][1] == {"value": 19}

    def test_battery_low_alert_not_repeated(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        dev.handle_z2m_state({"temperature": 22, "battery": 15})
        mock_mqtt.publish.reset_mock()

        dev.handle_z2m_state({"temperature": 23, "battery": 14})
        # Should NOT publish battery_low again
        topics = [c[0][0] for c in mock_mqtt.publish.call_args_list]
        assert "office/main/sensor/z2m_test_01/battery_low" not in topics

    def test_battery_low_alert_resets_on_recovery(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        # Trigger low battery alert
        dev.handle_z2m_state({"temperature": 22, "battery": 10})
        assert dev._battery_low_alerted is True

        # Battery replaced / recovered
        dev.handle_z2m_state({"temperature": 22, "battery": 100})
        assert dev._battery_low_alerted is False

        # Should re-alert if it drops again
        mock_mqtt.publish.reset_mock()
        dev.handle_z2m_state({"temperature": 22, "battery": 5})
        topics = [c[0][0] for c in mock_mqtt.publish.call_args_list]
        assert "office/main/sensor/z2m_test_01/battery_low" in topics

    def test_no_alert_above_threshold(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        dev.handle_z2m_state({"temperature": 22, "battery": 80})

        topics = [c[0][0] for c in mock_mqtt.publish.call_args_list]
        assert "office/main/sensor/z2m_test_01/battery_low" not in topics

    def test_handle_z2m_availability_online(self, mock_mqtt, z2m_availability_online):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        dev.handle_z2m_availability(z2m_availability_online)
        assert dev._online is True

    def test_handle_z2m_availability_offline(self, mock_mqtt, z2m_availability_offline):
        dev = make_device(TempHumidityDevice, mock_mqtt)
        dev._online = True
        dev.handle_z2m_availability(z2m_availability_offline)
        assert dev._online is False

    def test_handle_mcp_request_get_status(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt, soms_device_id="z2m_s1")
        dev._last_state = {"temperature": 22.0}

        request = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {"name": "get_status", "arguments": {}},
            "id": "req-001",
        }
        dev.handle_mcp_request(request)

        mock_mqtt.publish.assert_called_once()
        topic = mock_mqtt.publish.call_args[0][0]
        resp = mock_mqtt.publish.call_args[0][1]
        assert topic == "mcp/z2m_s1/response/req-001"
        assert resp["result"] == {"temperature": 22.0}

    def test_handle_mcp_request_unknown_tool(self, mock_mqtt):
        dev = make_device(TempHumidityDevice, mock_mqtt, soms_device_id="z2m_s1")

        request = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {"name": "nonexistent_tool", "arguments": {}},
            "id": "req-002",
        }
        dev.handle_mcp_request(request)

        resp = mock_mqtt.publish.call_args[0][1]
        assert "error" in resp

    def test_handle_mcp_request_actuator_tool(self, mock_mqtt):
        """Actuator MCP tool call works end-to-end."""
        dev = make_device(PlugDevice, mock_mqtt, soms_device_id="z2m_p1")

        request = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {"name": "turn_on", "arguments": {}},
            "id": "req-003",
        }
        dev.handle_mcp_request(request)

        # Should publish Z2M set command AND MCP response
        mock_mqtt.publish_z2m_set.assert_called_once_with("test_device", {"state": "ON"})
        # Find MCP response call
        mcp_calls = [c for c in mock_mqtt.publish.call_args_list
                      if c[0][0].startswith("mcp/")]
        assert len(mcp_calls) == 1
        assert mcp_calls[0][0][1]["result"]["status"] == "ok"


# ── Channel aggregation tests ────────────────────────────────

class TestChannelAggregation:

    def test_count_mode_buffers_truthy_events(self, mock_mqtt):
        """Motion sensor: truthy events are counted, not published immediately."""
        dev = make_device(MotionDevice, mock_mqtt)
        dev.handle_z2m_state({"occupancy": True})
        dev.handle_z2m_state({"occupancy": True})
        dev.handle_z2m_state({"occupancy": True})

        # motion channel is in count mode — nothing published immediately
        topics = [c[0][0] for c in mock_mqtt.publish.call_args_list]
        assert "office/main/sensor/z2m_test_01/motion" not in topics

        # Buffer should have count=3
        assert dev._channel_buffer["motion"] == 3

    def test_count_mode_ignores_falsy_events(self, mock_mqtt):
        """Motion sensor: occupancy=false does not increment count."""
        dev = make_device(MotionDevice, mock_mqtt)
        dev.handle_z2m_state({"occupancy": True})
        dev.handle_z2m_state({"occupancy": False})
        dev.handle_z2m_state({"occupancy": True})

        assert dev._channel_buffer["motion"] == 2

    def test_count_mode_flush_publishes_count(self, mock_mqtt):
        """Flush publishes motion_count and resets counter."""
        dev = make_device(MotionDevice, mock_mqtt)
        dev.handle_z2m_state({"occupancy": True})
        dev.handle_z2m_state({"occupancy": True})
        dev.handle_z2m_state({"occupancy": True})
        mock_mqtt.publish.reset_mock()

        dev.flush_channels()

        mock_mqtt.publish.assert_called_once_with(
            "office/main/sensor/z2m_test_01/motion_count", {"value": 3}
        )
        # Counter reset
        assert dev._channel_buffer["motion"] == 0

    def test_count_mode_flush_zero_after_no_events(self, mock_mqtt):
        """Flush with no events since last flush publishes 0."""
        dev = make_device(MotionDevice, mock_mqtt)
        # Trigger one event then flush
        dev.handle_z2m_state({"occupancy": True})
        dev.flush_channels()
        mock_mqtt.publish.reset_mock()

        # Flush again with no new events
        dev.flush_channels()

        mock_mqtt.publish.assert_called_once_with(
            "office/main/sensor/z2m_test_01/motion_count", {"value": 0}
        )

    def test_latest_mode_buffers_value(self, mock_mqtt):
        """Illuminance sensor: latest mode buffers, not publishes immediately."""
        dev = make_device(IlluminanceDevice, mock_mqtt)
        dev.handle_z2m_state({"illuminance": 190})
        dev.handle_z2m_state({"illuminance": 200})

        # Nothing published immediately for aggregated channel
        assert mock_mqtt.publish.call_count == 0

        # Buffer holds latest value
        assert dev._channel_buffer["illuminance"] == 200

    def test_latest_mode_flush_publishes_held_value(self, mock_mqtt):
        """Flush publishes the latest held value."""
        dev = make_device(IlluminanceDevice, mock_mqtt)
        dev.handle_z2m_state({"illuminance": 190})
        dev.handle_z2m_state({"illuminance": 200})
        mock_mqtt.publish.reset_mock()

        dev.flush_channels()

        mock_mqtt.publish.assert_called_once_with(
            "office/main/sensor/z2m_test_01/illuminance", {"value": 200}
        )

    def test_latest_mode_flush_repeats_unchanged_value(self, mock_mqtt):
        """Flush publishes even if no new data arrived (value unchanged)."""
        dev = make_device(IlluminanceDevice, mock_mqtt)
        dev.handle_z2m_state({"illuminance": 190})
        dev.flush_channels()
        mock_mqtt.publish.reset_mock()

        # No new data — flush again
        dev.flush_channels()

        mock_mqtt.publish.assert_called_once_with(
            "office/main/sensor/z2m_test_01/illuminance", {"value": 190}
        )

    def test_presence_latest_mode(self, mock_mqtt):
        """Presence sensor uses latest mode for motion channel."""
        dev = make_device(PresenceDevice, mock_mqtt)
        dev.handle_z2m_state({"presence": True})

        # Buffered, not published immediately
        assert mock_mqtt.publish.call_count == 0
        assert dev._channel_buffer["motion"] == 1

        dev.flush_channels()
        mock_mqtt.publish.assert_called_once_with(
            "office/main/sensor/z2m_test_01/motion", {"value": 1}
        )

    def test_passthrough_channels_publish_immediately(self, mock_mqtt):
        """Channels without aggregation (e.g. plug power_state) publish immediately."""
        dev = make_device(PlugDevice, mock_mqtt)
        dev.handle_z2m_state({"state": "ON"})

        mock_mqtt.publish.assert_called_once_with(
            "office/main/sensor/z2m_test_01/power_state", {"value": 1}
        )

    def test_temp_humidity_passthrough(self, mock_mqtt):
        """TempHumidity has no aggregation — all channels publish immediately."""
        dev = make_device(TempHumidityDevice, mock_mqtt)
        dev.handle_z2m_state({"temperature": 22.5, "humidity": 55})

        assert mock_mqtt.publish.call_count == 2
        assert dev._channel_buffer == {}

    def test_flush_with_no_buffer_is_noop(self, mock_mqtt):
        """Flush on device with empty buffer does nothing."""
        dev = make_device(TempHumidityDevice, mock_mqtt)
        dev.flush_channels()
        mock_mqtt.publish.assert_not_called()
