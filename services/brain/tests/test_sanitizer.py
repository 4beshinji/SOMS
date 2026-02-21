"""Unit tests for brain sanitizer — input validation for tool calls."""
import time
from unittest.mock import patch

import pytest

from sanitizer import Sanitizer


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def sanitizer():
    """Fresh Sanitizer instance for each test."""
    return Sanitizer()


# ── Query tools (always allowed) ─────────────────────────────────


class TestQueryTools:
    """Query/read-only tools should always pass validation."""

    def test_get_zone_status_allowed(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("get_zone_status", {"zone_id": "main"})
        assert ok is True
        assert "always allowed" in reason.lower()

    def test_get_active_tasks_allowed(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("get_active_tasks", {})
        assert ok is True

    def test_get_device_status_allowed(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("get_device_status", {"zone_id": "main"})
        assert ok is True


# ── Unknown tool ──────────────────────────────────────────────────


class TestUnknownTool:
    """Unknown tool names must be rejected."""

    def test_unknown_tool_rejected(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("hack_mainframe", {})
        assert ok is False
        assert "Unknown tool" in reason

    def test_unknown_tool_contains_name(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("delete_all", {})
        assert "delete_all" in reason


# ── create_task validation ────────────────────────────────────────


class TestCreateTask:
    """Validation rules for create_task."""

    def test_valid_task_passes(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("create_task", {
            "title": "Clean up", "description": "Please clean the desk",
            "bounty": 1000, "urgency": 2,
        })
        assert ok is True
        assert reason == "OK"

    def test_bounty_at_maximum_passes(self, sanitizer):
        ok, _ = sanitizer.validate_tool_call("create_task", {"bounty": 5000})
        assert ok is True

    def test_bounty_exceeds_maximum_rejected(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("create_task", {"bounty": 5001})
        assert ok is False
        assert "5000" in reason

    def test_bounty_way_over_limit(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("create_task", {"bounty": 999999})
        assert ok is False

    def test_bounty_zero_passes(self, sanitizer):
        ok, _ = sanitizer.validate_tool_call("create_task", {"bounty": 0})
        assert ok is True

    def test_bounty_float_over_limit(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("create_task", {"bounty": 5000.01})
        assert ok is False

    def test_urgency_valid_range(self, sanitizer):
        for urgency in range(5):
            ok, _ = sanitizer.validate_tool_call("create_task", {"urgency": urgency})
            assert ok is True, f"urgency={urgency} should pass"

    def test_urgency_negative_rejected(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("create_task", {"urgency": -1})
        assert ok is False
        assert "must be between 0 and 4" in reason

    def test_urgency_too_high_rejected(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("create_task", {"urgency": 5})
        assert ok is False
        assert "must be between 0 and 4" in reason

    def test_missing_bounty_uses_default(self, sanitizer):
        """Missing bounty defaults to 0 which is <= 5000."""
        ok, _ = sanitizer.validate_tool_call("create_task", {"title": "test"})
        assert ok is True

    def test_missing_urgency_uses_default(self, sanitizer):
        """Missing urgency defaults to 2 which is in range."""
        ok, _ = sanitizer.validate_tool_call("create_task", {"title": "test"})
        assert ok is True

    def test_rate_limit_enforced(self, sanitizer):
        """After max tasks per hour, new tasks are rejected."""
        for _ in range(sanitizer._max_tasks_per_hour):
            sanitizer.record_task_created()

        ok, reason = sanitizer.validate_tool_call("create_task", {"bounty": 500})
        assert ok is False
        assert "Rate limit" in reason

    def test_rate_limit_old_entries_expire(self, sanitizer):
        """Tasks older than 1 hour do not count toward rate limit."""
        old_time = time.time() - 3601  # > 1 hour ago
        sanitizer._task_creation_times = [old_time] * sanitizer._max_tasks_per_hour
        ok, _ = sanitizer.validate_tool_call("create_task", {"bounty": 500})
        assert ok is True

    def test_record_task_created_appends(self, sanitizer):
        assert len(sanitizer._task_creation_times) == 0
        sanitizer.record_task_created()
        assert len(sanitizer._task_creation_times) == 1


# ── speak validation ──────────────────────────────────────────────


class TestSpeak:
    """Validation rules for the speak tool."""

    def test_valid_speak_passes(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("speak", {
            "message": "Hello office!", "zone": "main", "tone": "neutral",
        })
        assert ok is True

    def test_empty_message_rejected(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("speak", {"message": ""})
        assert ok is False
        assert "empty" in reason.lower()

    def test_whitespace_only_message_rejected(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("speak", {"message": "   "})
        assert ok is False

    def test_missing_message_rejected(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("speak", {})
        assert ok is False

    def test_speak_cooldown_enforced(self, sanitizer):
        """Second speak to the same zone within cooldown is rejected."""
        sanitizer.record_speak("main")
        ok, reason = sanitizer.validate_tool_call("speak", {
            "message": "Hello again", "zone": "main",
        })
        assert ok is False
        assert "cooldown" in reason.lower()

    def test_speak_different_zone_passes(self, sanitizer):
        """Speak cooldown is per-zone."""
        sanitizer.record_speak("main")
        ok, _ = sanitizer.validate_tool_call("speak", {
            "message": "Hello kitchen", "zone": "kitchen",
        })
        assert ok is True

    def test_speak_cooldown_expires(self, sanitizer):
        """Speak is allowed after cooldown period expires."""
        sanitizer._speak_history["main"] = time.time() - sanitizer._speak_cooldown - 1
        ok, _ = sanitizer.validate_tool_call("speak", {
            "message": "Hello again", "zone": "main",
        })
        assert ok is True

    def test_speak_default_zone_is_general(self, sanitizer):
        """When zone is not specified, defaults to 'general'."""
        sanitizer.record_speak("general")
        ok, reason = sanitizer.validate_tool_call("speak", {"message": "Hello"})
        assert ok is False
        assert "general" in reason


# ── send_device_command validation ────────────────────────────────


class TestDeviceCommand:
    """Validation rules for send_device_command."""

    def test_allowed_device_passes(self, sanitizer):
        ok, _ = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "light_01", "tool_name": "toggle_light",
        })
        assert ok is True

    def test_disallowed_device_rejected(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "rogue_device", "tool_name": "toggle",
        })
        assert ok is False
        assert "not in the allowed device list" in reason

    def test_swarm_hub_always_allowed(self, sanitizer):
        """Devices starting with 'swarm_hub' bypass allowlist."""
        ok, _ = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "swarm_hub_99", "tool_name": "read_sensor",
        })
        assert ok is True

    def test_temperature_in_range_passes(self, sanitizer):
        ok, _ = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "light_01", "tool_name": "set_temperature",
            "arguments": '{"temperature": 24}',
        })
        assert ok is True

    def test_temperature_too_low_rejected(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "light_01", "tool_name": "set_temperature",
            "arguments": '{"temperature": 10}',
        })
        assert ok is False
        assert "out of safe range" in reason

    def test_temperature_too_high_rejected(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "light_01", "tool_name": "set_temperature",
            "arguments": '{"temperature": 35}',
        })
        assert ok is False

    def test_temperature_at_min_boundary(self, sanitizer):
        ok, _ = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "light_01", "tool_name": "set_temperature",
            "arguments": '{"temperature": 18}',
        })
        assert ok is True

    def test_temperature_at_max_boundary(self, sanitizer):
        ok, _ = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "light_01", "tool_name": "set_temperature",
            "arguments": '{"temperature": 28}',
        })
        assert ok is True

    def test_pump_duration_in_range_passes(self, sanitizer):
        ok, _ = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "pump_01", "tool_name": "run_pump",
            "arguments": '{"duration": 30}',
        })
        assert ok is True

    def test_pump_duration_too_long_rejected(self, sanitizer):
        ok, reason = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "pump_01", "tool_name": "run_pump",
            "arguments": '{"duration": 120}',
        })
        assert ok is False
        assert "exceeds maximum" in reason

    def test_pump_duration_at_max_passes(self, sanitizer):
        ok, _ = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "pump_01", "tool_name": "run_pump",
            "arguments": '{"duration": 60}',
        })
        assert ok is True

    def test_arguments_as_dict(self, sanitizer):
        """Arguments can be passed as a dict instead of JSON string."""
        ok, _ = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "light_01", "tool_name": "set_temperature",
            "arguments": {"temperature": 24},
        })
        assert ok is True

    def test_arguments_invalid_json_treated_as_empty(self, sanitizer):
        """Invalid JSON string for arguments falls back to empty dict."""
        ok, _ = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "light_01", "tool_name": "set_temperature",
            "arguments": "not_json{{{",
        })
        # No temperature in parsed args, so set_temperature check passes (temp is None)
        assert ok is True

    def test_no_arguments_key(self, sanitizer):
        """Missing arguments key is fine for non-parameterised commands."""
        ok, _ = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "light_01", "tool_name": "toggle_light",
        })
        assert ok is True
