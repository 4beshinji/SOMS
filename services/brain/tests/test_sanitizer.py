"""Unit tests for brain sanitizer — input validation for tool calls."""
import time
from unittest.mock import patch, MagicMock

import pytest

from sanitizer import Sanitizer


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def sanitizer():
    """Fresh Sanitizer instance for each test."""
    return Sanitizer()


@pytest.fixture
def sanitizer_with_inventory():
    """Sanitizer with a mock inventory tracker that has registered items."""
    s = Sanitizer()
    tracker = MagicMock()
    tracker.get_registered_item_names.return_value = {"コーヒー豆", "コピー用紙", "トイレットペーパー"}
    s.set_inventory_tracker(tracker)
    return s


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

    @pytest.mark.parametrize("bounty, expected_ok", [
        (5000, True),
        (5001, False),
        (0, True),
        (5000.01, False),
    ])
    def test_bounty_validation(self, sanitizer, bounty, expected_ok):
        ok, reason = sanitizer.validate_tool_call("create_task", {"bounty": bounty})
        assert ok is expected_ok
        if not expected_ok:
            assert "5000" in reason

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

    @pytest.mark.parametrize("temp, expected_ok", [
        (24, True),
        (10, False),
        (35, False),
        (18, True),
        (28, True),
    ])
    def test_temperature_boundaries(self, sanitizer, temp, expected_ok):
        ok, reason = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "light_01", "tool_name": "set_temperature",
            "arguments": f'{{"temperature": {temp}}}',
        })
        assert ok is expected_ok
        if not expected_ok:
            assert "out of safe range" in reason

    @pytest.mark.parametrize("duration, expected_ok", [
        (30, True),
        (120, False),
        (60, True),
    ])
    def test_pump_duration_validation(self, sanitizer, duration, expected_ok):
        ok, reason = sanitizer.validate_tool_call("send_device_command", {
            "agent_id": "pump_01", "tool_name": "run_pump",
            "arguments": f'{{"duration": {duration}}}',
        })
        assert ok is expected_ok
        if not expected_ok:
            assert "exceeds maximum" in reason

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


# ── add_shopping_item validation ─────────────────────────────────


class TestAddShoppingItem:
    """Validation rules for add_shopping_item with inventory whitelist."""

    def test_registered_item_allowed(self, sanitizer_with_inventory):
        ok, reason = sanitizer_with_inventory.validate_tool_call(
            "add_shopping_item", {"name": "コーヒー豆", "quantity": 3},
        )
        assert ok is True

    def test_unregistered_item_rejected(self, sanitizer_with_inventory):
        ok, reason = sanitizer_with_inventory.validate_tool_call(
            "add_shopping_item", {"name": "謎のアイテム", "quantity": 1},
        )
        assert ok is False
        assert "登録されていません" in reason

    def test_empty_name_rejected(self, sanitizer_with_inventory):
        ok, reason = sanitizer_with_inventory.validate_tool_call(
            "add_shopping_item", {"name": "", "quantity": 1},
        )
        assert ok is False
        assert "空" in reason

    def test_without_tracker_allows_any_item(self, sanitizer):
        """Without inventory tracker, any item name is accepted (fallback)."""
        ok, reason = sanitizer.validate_tool_call(
            "add_shopping_item", {"name": "何でも追加", "quantity": 1},
        )
        assert ok is True

    def test_quantity_out_of_range_rejected(self, sanitizer_with_inventory):
        ok, reason = sanitizer_with_inventory.validate_tool_call(
            "add_shopping_item", {"name": "コーヒー豆", "quantity": 101},
        )
        assert ok is False
        assert "範囲外" in reason

    def test_rate_limit_enforced(self, sanitizer_with_inventory):
        for _ in range(sanitizer_with_inventory._max_shopping_per_hour):
            sanitizer_with_inventory.record_shopping_item_added()

        ok, reason = sanitizer_with_inventory.validate_tool_call(
            "add_shopping_item", {"name": "コーヒー豆", "quantity": 1},
        )
        assert ok is False
        assert "レート制限" in reason
