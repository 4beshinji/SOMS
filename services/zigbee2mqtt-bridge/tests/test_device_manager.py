"""Unit tests for device_manager.py — device creation, heartbeats, flush loop."""
import asyncio
from unittest.mock import MagicMock

import pytest

from device_manager import DeviceManager


# ── DeviceManager.__init__ tests ───────────────────────────────

class TestDeviceManagerInit:
    """Tests for DeviceManager initialization."""

    def test_initial_devices_empty(self, sample_config, mock_mqtt):
        dm = DeviceManager(sample_config, mock_mqtt)
        assert dm.devices == {}

    def test_empty_config(self, mock_mqtt):
        dm = DeviceManager({}, mock_mqtt)
        assert dm.devices == {}

    def test_default_flush_interval(self, sample_config, mock_mqtt):
        dm = DeviceManager(sample_config, mock_mqtt)
        assert dm._flush_interval == 30

    def test_custom_flush_interval(self, mock_mqtt):
        config = {"flush_interval_sec": 10}
        dm = DeviceManager(config, mock_mqtt)
        assert dm._flush_interval == 10


# ── DeviceManager.create_devices tests ─────────────────────────

class TestCreateDevices:
    """Tests for device instantiation from config."""

    def test_creates_all_device_types(self, sample_config, mock_mqtt):
        dm = DeviceManager(sample_config, mock_mqtt)
        dm.create_devices()

        assert len(dm.devices) == 5
        assert "z2m_temp_01" in dm.devices
        assert "z2m_motion_01" in dm.devices
        assert "z2m_door_01" in dm.devices
        assert "z2m_plug_01" in dm.devices
        assert "z2m_light_01" in dm.devices

    def test_skips_unknown_device_type(self, mock_mqtt):
        config = {
            "devices": [
                {
                    "type": "nonexistent_type",
                    "z2m_friendly_name": "bad_device",
                    "soms_device_id": "bad_01",
                    "zone": "main",
                },
            ]
        }
        dm = DeviceManager(config, mock_mqtt)
        dm.create_devices()
        assert len(dm.devices) == 0

    def test_registers_device_with_mqtt(self, sample_config, mock_mqtt):
        dm = DeviceManager(sample_config, mock_mqtt)
        dm.create_devices()

        assert mock_mqtt.register_device.call_count == 5

    def test_registers_z2m_name_with_mqtt(self, sample_config, mock_mqtt):
        dm = DeviceManager(sample_config, mock_mqtt)
        dm.create_devices()

        assert mock_mqtt.register_z2m_device.call_count == 5

    def test_device_properties_set_correctly(self, sample_config, mock_mqtt):
        dm = DeviceManager(sample_config, mock_mqtt)
        dm.create_devices()

        temp = dm.devices["z2m_temp_01"]
        assert temp.z2m_friendly_name == "living_room_sensor"
        assert temp.soms_device_id == "z2m_temp_01"
        assert temp.zone == "main"
        assert temp.label == "温湿度センサー"

    def test_empty_devices_list(self, mock_mqtt):
        config = {"devices": []}
        dm = DeviceManager(config, mock_mqtt)
        dm.create_devices()
        assert len(dm.devices) == 0

    def test_no_devices_key_in_config(self, mock_mqtt):
        config = {"z2m_base_topic": "zigbee2mqtt"}
        dm = DeviceManager(config, mock_mqtt)
        dm.create_devices()
        assert len(dm.devices) == 0

    def test_device_default_zone(self, mock_mqtt):
        config = {
            "devices": [
                {
                    "type": "temp_humidity",
                    "z2m_friendly_name": "sensor",
                    "soms_device_id": "z2m_no_zone",
                },
            ]
        }
        dm = DeviceManager(config, mock_mqtt)
        dm.create_devices()
        assert dm.devices["z2m_no_zone"].zone == "main"

    def test_device_default_label(self, mock_mqtt):
        config = {
            "devices": [
                {
                    "type": "temp_humidity",
                    "z2m_friendly_name": "sensor",
                    "soms_device_id": "z2m_no_label",
                    "zone": "main",
                },
            ]
        }
        dm = DeviceManager(config, mock_mqtt)
        dm.create_devices()
        assert dm.devices["z2m_no_label"].label == ""

    def test_mixed_valid_and_invalid_devices(self, mock_mqtt):
        config = {
            "devices": [
                {
                    "type": "temp_humidity",
                    "z2m_friendly_name": "good_sensor",
                    "soms_device_id": "z2m_good",
                    "zone": "main",
                },
                {
                    "type": "invalid_type",
                    "z2m_friendly_name": "bad_sensor",
                    "soms_device_id": "z2m_bad",
                    "zone": "main",
                },
            ]
        }
        dm = DeviceManager(config, mock_mqtt)
        dm.create_devices()
        assert len(dm.devices) == 1
        assert "z2m_good" in dm.devices


# ── DeviceManager.heartbeat_loop tests ─────────────────────────

class TestHeartbeatLoop:
    """Tests for the heartbeat_loop method."""

    @pytest.mark.asyncio
    async def test_heartbeat_publishes_for_all_devices(self, sample_config, mock_mqtt):
        dm = DeviceManager(sample_config, mock_mqtt)
        dm.create_devices()

        for dev in dm.devices.values():
            dev.publish_heartbeat = MagicMock()

        async def run_one_iteration():
            task = asyncio.create_task(dm.heartbeat_loop())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_one_iteration()

        for dev in dm.devices.values():
            dev.publish_heartbeat.assert_called()


# ── DeviceManager.flush_loop tests ─────────────────────────────

class TestFlushLoop:
    """Tests for the flush_loop method."""

    @pytest.mark.asyncio
    async def test_flush_calls_flush_channels_on_aggregated_devices(self, mock_mqtt):
        """flush_loop calls flush_channels on devices with aggregation."""
        config = {
            "flush_interval_sec": 0.05,
            "devices": [
                {
                    "type": "motion",
                    "z2m_friendly_name": "m1",
                    "soms_device_id": "z2m_m1",
                    "zone": "main",
                },
                {
                    "type": "temp_humidity",
                    "z2m_friendly_name": "t1",
                    "soms_device_id": "z2m_t1",
                    "zone": "main",
                },
            ],
        }
        dm = DeviceManager(config, mock_mqtt)
        dm.create_devices()

        for dev in dm.devices.values():
            dev.flush_channels = MagicMock()

        task = asyncio.create_task(dm.flush_loop())
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # motion has aggregation — flush_channels should be called
        dm.devices["z2m_m1"].flush_channels.assert_called()
        # temp_humidity has no aggregation — flush_channels should NOT be called
        dm.devices["z2m_t1"].flush_channels.assert_not_called()


# ── Auto-register tests ───────────────────────────────────────

class TestAutoRegister:
    """Tests for auto-registering new Z2M devices at runtime."""

    def test_auto_register_new_device(self, mock_mqtt):
        dm = DeviceManager({"devices": []}, mock_mqtt)
        dm.create_devices()
        assert len(dm.devices) == 0

        z2m_device = {
            "friendly_name": "0xaabbcc",
            "ieee_address": "0xaabbcc",
            "type": "EndDevice",
            "definition": {
                "model": "TS0601",
                "description": "Temp/humidity sensor",
                "vendor": "Tuya",
            },
        }
        result = dm.auto_register(z2m_device)
        assert result is True
        assert len(dm.devices) == 1
        # Auto-generated SOMS ID
        dev = list(dm.devices.values())[0]
        assert dev.z2m_friendly_name == "0xaabbcc"
        assert dev.soms_device_id.startswith("z2m_auto_")

    def test_auto_register_skips_already_registered(self, sample_config, mock_mqtt):
        dm = DeviceManager(sample_config, mock_mqtt)
        dm.create_devices()
        count_before = len(dm.devices)

        z2m_device = {
            "friendly_name": "living_room_sensor",  # already in config
            "ieee_address": "0xaaa",
            "type": "EndDevice",
        }
        result = dm.auto_register(z2m_device)
        assert result is False
        assert len(dm.devices) == count_before

    def test_auto_register_skips_coordinator(self, mock_mqtt):
        dm = DeviceManager({"devices": []}, mock_mqtt)
        dm.create_devices()

        z2m_device = {
            "friendly_name": "Coordinator",
            "ieee_address": "0x00",
            "type": "Coordinator",
        }
        result = dm.auto_register(z2m_device)
        assert result is False
        assert len(dm.devices) == 0

    def test_auto_register_uses_generic_sensor(self, mock_mqtt):
        """Auto-registered device uses GenericSensorDevice."""
        dm = DeviceManager({"devices": []}, mock_mqtt)
        dm.create_devices()

        z2m_device = {
            "friendly_name": "0xnew",
            "ieee_address": "0xnew",
            "type": "EndDevice",
            "definition": {"description": "Unknown gadget"},
        }
        dm.auto_register(z2m_device)
        dev = list(dm.devices.values())[0]
        assert dev.device_type == "generic_sensor"

    def test_auto_register_publishes_on_mqtt(self, mock_mqtt):
        """Auto-registered device should be registered with MQTT bridge."""
        dm = DeviceManager({"devices": []}, mock_mqtt)
        dm.create_devices()
        mock_mqtt.register_device.reset_mock()
        mock_mqtt.register_z2m_device.reset_mock()

        z2m_device = {
            "friendly_name": "0xnew",
            "ieee_address": "0xnew",
            "type": "EndDevice",
        }
        dm.auto_register(z2m_device)
        mock_mqtt.register_device.assert_called_once()
        mock_mqtt.register_z2m_device.assert_called_once()
