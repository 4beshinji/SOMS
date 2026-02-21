"""Unit tests for device_manager.py — device creation, polling, heartbeats."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from device_manager import DeviceManager


# ── DeviceManager.__init__ tests ───────────────────────────────

class TestDeviceManagerInit:
    """Tests for DeviceManager initialization and config parsing."""

    def test_default_polling_intervals(self, sample_config, mock_api, mock_mqtt):
        """Polling intervals are read from config."""
        dm = DeviceManager(sample_config, mock_api, mock_mqtt)
        assert dm._sensor_interval == 120
        assert dm._actuator_interval == 300
        assert dm._stagger_ms == 200

    def test_default_polling_without_config(self, mock_api, mock_mqtt):
        """Defaults are used when polling config is absent."""
        dm = DeviceManager({}, mock_api, mock_mqtt)
        assert dm._sensor_interval == 120
        assert dm._actuator_interval == 300
        assert dm._stagger_ms == 200

    def test_custom_polling_intervals(self, mock_api, mock_mqtt):
        """Custom polling intervals from config are used."""
        config = {
            "polling": {
                "sensor_interval_sec": 60,
                "actuator_interval_sec": 600,
                "stagger_delay_ms": 500,
            }
        }
        dm = DeviceManager(config, mock_api, mock_mqtt)
        assert dm._sensor_interval == 60
        assert dm._actuator_interval == 600
        assert dm._stagger_ms == 500

    def test_initial_devices_empty(self, sample_config, mock_api, mock_mqtt):
        """Devices dict is empty before create_devices() is called."""
        dm = DeviceManager(sample_config, mock_api, mock_mqtt)
        assert dm.devices == {}


# ── DeviceManager.create_devices tests ─────────────────────────

class TestCreateDevices:
    """Tests for device instantiation from config."""

    def test_creates_known_device_types(self, sample_config, mock_api, mock_mqtt):
        """Known device types in config are instantiated."""
        dm = DeviceManager(sample_config, mock_api, mock_mqtt)
        dm.create_devices()

        assert len(dm.devices) == 3
        assert "switchbot_meter_01" in dm.devices
        assert "switchbot_bot_01" in dm.devices
        assert "switchbot_motion_01" in dm.devices

    def test_skips_unknown_device_type(self, mock_api, mock_mqtt):
        """Unknown device types are skipped with a warning."""
        config = {
            "devices": [
                {
                    "type": "nonexistent_device_type",
                    "switchbot_id": "ABC123",
                    "soms_device_id": "bad_device",
                    "zone": "main",
                },
            ]
        }
        dm = DeviceManager(config, mock_api, mock_mqtt)
        dm.create_devices()
        assert len(dm.devices) == 0

    def test_registers_device_with_mqtt(self, sample_config, mock_api, mock_mqtt):
        """Each created device is registered with the MQTT bridge."""
        dm = DeviceManager(sample_config, mock_api, mock_mqtt)
        dm.create_devices()

        # register_device should be called once per device
        assert mock_mqtt.register_device.call_count == 3

    def test_device_properties_set_correctly(self, sample_config, mock_api, mock_mqtt):
        """Device instances have correct attributes from config."""
        dm = DeviceManager(sample_config, mock_api, mock_mqtt)
        dm.create_devices()

        meter = dm.devices["switchbot_meter_01"]
        assert meter.switchbot_id == "AABBCCDDEE01"
        assert meter.soms_device_id == "switchbot_meter_01"
        assert meter.zone == "main"
        assert meter.label == "Office Thermometer"

    def test_empty_devices_list(self, mock_api, mock_mqtt):
        """No devices are created when config has empty devices list."""
        config = {"devices": []}
        dm = DeviceManager(config, mock_api, mock_mqtt)
        dm.create_devices()
        assert len(dm.devices) == 0

    def test_no_devices_key_in_config(self, mock_api, mock_mqtt):
        """No crash when config lacks 'devices' key entirely."""
        config = {"polling": {"sensor_interval_sec": 60}}
        dm = DeviceManager(config, mock_api, mock_mqtt)
        dm.create_devices()
        assert len(dm.devices) == 0

    def test_device_default_zone(self, mock_api, mock_mqtt):
        """Devices default to zone 'main' when zone is not specified."""
        config = {
            "devices": [
                {
                    "type": "meter",
                    "switchbot_id": "ABC",
                    "soms_device_id": "meter_no_zone",
                },
            ]
        }
        dm = DeviceManager(config, mock_api, mock_mqtt)
        dm.create_devices()
        assert dm.devices["meter_no_zone"].zone == "main"


# ── DeviceManager._poll_all tests ──────────────────────────────

class TestPollAll:
    """Tests for the _poll_all method."""

    @pytest.mark.asyncio
    async def test_poll_all_calls_poll_status_on_each_device(self, sample_config, mock_api, mock_mqtt):
        """_poll_all() calls poll_status() on every device."""
        dm = DeviceManager(sample_config, mock_api, mock_mqtt)
        dm.create_devices()

        for dev in dm.devices.values():
            dev.poll_status = AsyncMock(return_value={})

        await dm._poll_all()

        for dev in dm.devices.values():
            dev.poll_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_all_skips_recently_polled_actuators(self, mock_api, mock_mqtt):
        """Actuator devices that were recently polled are skipped."""
        config = {
            "polling": {
                "sensor_interval_sec": 120,
                "actuator_interval_sec": 300,
                "stagger_delay_ms": 0,
            },
            "devices": [
                {
                    "type": "bot",
                    "switchbot_id": "BOT01",
                    "soms_device_id": "bot_01",
                    "zone": "main",
                },
            ],
        }
        dm = DeviceManager(config, mock_api, mock_mqtt)
        dm.create_devices()

        bot = dm.devices["bot_01"]
        bot.poll_status = AsyncMock(return_value={})

        # Simulate a recent poll (within actuator_interval)
        bot._last_poll = time.time() - 10  # 10 seconds ago, well within 300s

        await dm._poll_all()

        # Bot is not a sensor, was recently polled, so should be skipped
        bot.poll_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_all_does_not_skip_sensor_devices(self, mock_api, mock_mqtt):
        """Sensor devices are always polled regardless of _last_poll."""
        config = {
            "polling": {
                "sensor_interval_sec": 120,
                "actuator_interval_sec": 300,
                "stagger_delay_ms": 0,
            },
            "devices": [
                {
                    "type": "meter",
                    "switchbot_id": "METER01",
                    "soms_device_id": "meter_01",
                    "zone": "main",
                },
            ],
        }
        dm = DeviceManager(config, mock_api, mock_mqtt)
        dm.create_devices()

        meter = dm.devices["meter_01"]
        meter.poll_status = AsyncMock(return_value={})
        meter._last_poll = time.time() - 10  # recently polled

        await dm._poll_all()

        # Meter is a sensor, so it should always be polled
        meter.poll_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_all_polls_actuator_on_first_call(self, mock_api, mock_mqtt):
        """Actuator with _last_poll == 0 (never polled) is always polled."""
        config = {
            "polling": {
                "sensor_interval_sec": 120,
                "actuator_interval_sec": 300,
                "stagger_delay_ms": 0,
            },
            "devices": [
                {
                    "type": "bot",
                    "switchbot_id": "BOT01",
                    "soms_device_id": "bot_01",
                    "zone": "main",
                },
            ],
        }
        dm = DeviceManager(config, mock_api, mock_mqtt)
        dm.create_devices()

        bot = dm.devices["bot_01"]
        bot.poll_status = AsyncMock(return_value={})
        # _last_poll defaults to 0 (never polled)

        await dm._poll_all()

        # First poll should always happen
        bot.poll_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_all_polls_actuator_after_interval_elapsed(self, mock_api, mock_mqtt):
        """Actuator is polled when actuator_interval has elapsed since last poll."""
        config = {
            "polling": {
                "sensor_interval_sec": 120,
                "actuator_interval_sec": 300,
                "stagger_delay_ms": 0,
            },
            "devices": [
                {
                    "type": "bot",
                    "switchbot_id": "BOT01",
                    "soms_device_id": "bot_01",
                    "zone": "main",
                },
            ],
        }
        dm = DeviceManager(config, mock_api, mock_mqtt)
        dm.create_devices()

        bot = dm.devices["bot_01"]
        bot.poll_status = AsyncMock(return_value={})
        # Simulate that the actuator was polled 301 seconds ago (past 300s interval)
        bot._last_poll = time.time() - 301

        await dm._poll_all()

        bot.poll_status.assert_called_once()


# ── DeviceManager.heartbeat_loop tests ─────────────────────────

class TestHeartbeatLoop:
    """Tests for the heartbeat_loop method."""

    @pytest.mark.asyncio
    async def test_heartbeat_publishes_for_all_devices(self, sample_config, mock_api, mock_mqtt):
        """heartbeat_loop publishes heartbeats for every device."""
        dm = DeviceManager(sample_config, mock_api, mock_mqtt)
        dm.create_devices()

        for dev in dm.devices.values():
            dev.publish_heartbeat = MagicMock()

        # Run one iteration of the heartbeat loop then cancel
        async def run_one_iteration():
            task = asyncio.create_task(dm.heartbeat_loop())
            # Let the loop publish once then cancel
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_one_iteration()

        for dev in dm.devices.values():
            dev.publish_heartbeat.assert_called()


# ── DeviceManager.poll_loop tests ──────────────────────────────

class TestPollLoop:
    """Tests for the poll_loop method."""

    @pytest.mark.asyncio
    async def test_poll_loop_calls_poll_all_initially(self, sample_config, mock_api, mock_mqtt):
        """poll_loop calls _poll_all on startup before entering the loop."""
        dm = DeviceManager(sample_config, mock_api, mock_mqtt)
        dm.create_devices()
        dm._poll_all = AsyncMock()

        async def run_one_iteration():
            task = asyncio.create_task(dm.poll_loop())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_one_iteration()

        # _poll_all should have been called at least once (the initial poll)
        dm._poll_all.assert_called()
