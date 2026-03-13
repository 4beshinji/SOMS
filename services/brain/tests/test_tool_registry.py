"""Unit tests for brain tool_registry — tool schema definitions."""
import pytest

from tool_registry import TOOLS, get_tools, get_tool_names


# ── Schema structure ──────────────────────────────────────────────


class TestToolSchemaStructure:
    """Every tool entry must follow the OpenAI function-calling schema."""

    def test_no_duplicate_tool_names(self):
        names = get_tool_names()
        assert len(names) == len(set(names)), f"Duplicate names found: {names}"


# ── get_tools / get_tool_names ────────────────────────────────────


class TestGetters:
    """Helper function outputs."""

    def test_get_tool_names_returns_strings(self):
        names = get_tool_names()
        assert all(isinstance(n, str) for n in names)

    def test_expected_tool_names(self):
        """All six documented tools must be present."""
        names = set(get_tool_names())
        expected = {
            "create_task",
            "send_device_command",
            "get_zone_status",
            "speak",
            "get_active_tasks",
            "get_device_status",
            "check_inventory",
            "add_shopping_item",
            "calibrate_shelf",
        }
        assert expected == names


# ── Required fields per tool ──────────────────────────────────────


def _get_tool_def(name: str) -> dict:
    """Return the function definition for a named tool."""
    for tool in TOOLS:
        if tool["function"]["name"] == name:
            return tool["function"]
    raise KeyError(f"Tool '{name}' not found")


class TestRequiredFields:
    """Verify 'required' property arrays on each tool."""

    def test_create_task_required_fields(self):
        fn = _get_tool_def("create_task")
        assert "required" in fn["parameters"]
        req = fn["parameters"]["required"]
        assert "title" in req
        assert "description" in req

    def test_send_device_command_required_fields(self):
        fn = _get_tool_def("send_device_command")
        req = fn["parameters"]["required"]
        assert "agent_id" in req
        assert "tool_name" in req

    def test_get_zone_status_required_fields(self):
        fn = _get_tool_def("get_zone_status")
        req = fn["parameters"]["required"]
        assert "zone_id" in req

    def test_speak_required_fields(self):
        fn = _get_tool_def("speak")
        req = fn["parameters"]["required"]
        assert "message" in req

    def test_get_active_tasks_no_required_fields(self):
        fn = _get_tool_def("get_active_tasks")
        params = fn["parameters"]
        # Either no "required" key or empty list
        req = params.get("required", [])
        assert len(req) == 0

    def test_get_device_status_no_required_fields(self):
        fn = _get_tool_def("get_device_status")
        req = fn["parameters"].get("required", [])
        assert len(req) == 0


# ── Property types ────────────────────────────────────────────────


class TestPropertyTypes:
    """Verify property type declarations are valid."""

    VALID_TYPES = {"string", "integer", "number", "boolean", "object", "array"}

    def test_all_property_types_are_valid(self):
        for tool in TOOLS:
            props = tool["function"]["parameters"]["properties"]
            for prop_name, prop_def in props.items():
                assert prop_def.get("type") in self.VALID_TYPES, (
                    f"Invalid type for {tool['function']['name']}.{prop_name}: "
                    f"{prop_def.get('type')}"
                )

