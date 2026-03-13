"""Unit tests for ToolExecutor — tool call routing, validation, and handlers.

Tests verify:
- Sanitizer validation gates all tool calls
- Each handler produces correct success/error responses
- Unknown tools are rejected
- Exceptions in handlers are caught gracefully
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tool_executor import ToolExecutor
from sanitizer import Sanitizer


# ── Helpers ─────────────────────────────────────────────────────


_SENTINEL = object()


def _make_executor(
    sanitizer=None,
    mcp_bridge=None,
    dashboard_client=None,
    world_model=None,
    task_queue=_SENTINEL,
    session=None,
    device_registry=None,
):
    """Create a ToolExecutor with configurable mocks."""
    if task_queue is _SENTINEL:
        task_queue = AsyncMock()
    return ToolExecutor(
        sanitizer=sanitizer or Sanitizer(),
        mcp_bridge=mcp_bridge or AsyncMock(),
        dashboard_client=dashboard_client or AsyncMock(),
        world_model=world_model or MagicMock(),
        task_queue=task_queue,
        session=session,
        device_registry=device_registry,
    )


def _mock_session_post(status=200, json_data=None):
    """Build an AsyncMock for aiohttp session.post context manager."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=cm)
    session.get = MagicMock(return_value=cm)
    return session


# ── Validation gate ─────────────────────────────────────────────


class TestValidationGate:
    """Sanitizer validation blocks unsafe tool calls."""

    @pytest.mark.asyncio
    async def test_rejected_by_sanitizer(self):
        sanitizer = Sanitizer()
        executor = _make_executor(sanitizer=sanitizer)
        # Bounty exceeds 5000 → rejected
        result = await executor.execute(
            "create_task",
            {"title": "Test", "bounty": 9999, "urgency": 2},
        )
        assert result["success"] is False
        assert "5000" in result["error"]

    @pytest.mark.asyncio
    async def test_unknown_tool_rejected(self):
        executor = _make_executor()
        result = await executor.execute("nonexistent_tool", {})
        assert result["success"] is False
        assert "Unknown tool" in result["error"]



# ── create_task ─────────────────────────────────────────────────


class TestCreateTask:

    @pytest.mark.asyncio
    async def test_create_task_success(self):
        dashboard = AsyncMock()
        dashboard.create_task = AsyncMock(return_value={"id": 42})
        sanitizer = Sanitizer()
        task_queue = AsyncMock()
        task_queue.add_task = AsyncMock()

        executor = _make_executor(
            sanitizer=sanitizer,
            dashboard_client=dashboard,
            task_queue=task_queue,
        )

        result = await executor.execute(
            "create_task",
            {"title": "Clean kitchen", "description": "Wipe counters", "bounty": 1500, "urgency": 3, "zone": "kitchen"},
        )

        assert result["success"] is True
        assert "42" in result["result"]
        assert "Clean kitchen" in result["result"]
        dashboard.create_task.assert_called_once()
        task_queue.add_task.assert_called_once_with(
            task_id=42, title="Clean kitchen", urgency=3, zone="kitchen"
        )

    @pytest.mark.asyncio
    async def test_create_task_records_rate_limit(self):
        dashboard = AsyncMock()
        dashboard.create_task = AsyncMock(return_value={"id": 1})
        sanitizer = Sanitizer()

        executor = _make_executor(sanitizer=sanitizer, dashboard_client=dashboard)
        await executor.execute(
            "create_task",
            {"title": "T", "description": "D", "bounty": 500, "urgency": 1},
        )
        assert len(sanitizer._task_creation_times) == 1

    @pytest.mark.asyncio
    async def test_create_task_dashboard_failure(self):
        dashboard = AsyncMock()
        dashboard.create_task = AsyncMock(return_value=None)

        executor = _make_executor(dashboard_client=dashboard)
        result = await executor.execute(
            "create_task",
            {"title": "Fail", "description": "D", "bounty": 500, "urgency": 1},
        )
        assert result["success"] is False
        assert "失敗" in result["error"]

    @pytest.mark.asyncio
    async def test_create_task_no_id_in_response(self):
        dashboard = AsyncMock()
        dashboard.create_task = AsyncMock(return_value={"status": "error"})

        executor = _make_executor(dashboard_client=dashboard)
        result = await executor.execute(
            "create_task",
            {"title": "No ID", "description": "D", "bounty": 500, "urgency": 1},
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_create_task_parses_task_types(self):
        dashboard = AsyncMock()
        dashboard.create_task = AsyncMock(return_value={"id": 10})

        executor = _make_executor(dashboard_client=dashboard, task_queue=AsyncMock())
        await executor.execute(
            "create_task",
            {"title": "T", "description": "D", "bounty": 500, "urgency": 1, "task_types": "supply, urgent"},
        )
        call_args = dashboard.create_task.call_args
        assert call_args.kwargs["task_types"] == ["supply", "urgent"]

    @pytest.mark.asyncio
    async def test_create_task_without_task_queue(self):
        dashboard = AsyncMock()
        dashboard.create_task = AsyncMock(return_value={"id": 5})
        sanitizer = Sanitizer()

        executor = _make_executor(
            sanitizer=sanitizer,
            dashboard_client=dashboard,
            task_queue=None,
        )
        result = await executor.execute(
            "create_task",
            {"title": "T", "description": "D", "bounty": 500, "urgency": 1},
        )
        assert result["success"] is True


# ── speak ────────────────────────────────────────────────────────


class TestSpeak:

    @pytest.mark.asyncio
    async def test_speak_success(self):
        session = _mock_session_post(200, {"audio_url": "/audio/test.mp3"})
        sanitizer = Sanitizer()

        executor = _make_executor(sanitizer=sanitizer, session=session)
        result = await executor.execute(
            "speak",
            {"message": "Hello everyone", "zone": "main", "tone": "neutral"},
        )

        assert result["success"] is True
        assert "Hello everyone" in result["result"]
        # Should record speak for cooldown
        assert "main" in sanitizer._speak_history

    @pytest.mark.asyncio
    async def test_speak_voice_service_failure(self):
        resp = AsyncMock()
        resp.status = 500
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=cm)

        executor = _make_executor(session=session)
        result = await executor.execute(
            "speak",
            {"message": "Test", "zone": "main"},
        )
        # Still succeeds (voice failure is non-fatal)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_speak_empty_message_rejected(self):
        executor = _make_executor()
        result = await executor.execute(
            "speak",
            {"message": "", "zone": "main"},
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_speak_cooldown_enforced(self):
        session = _mock_session_post(200, {"audio_url": "/audio/x.mp3"})
        sanitizer = Sanitizer()

        executor = _make_executor(sanitizer=sanitizer, session=session)
        # First speak succeeds
        r1 = await executor.execute("speak", {"message": "First", "zone": "z1"})
        assert r1["success"] is True

        # Second speak in same zone within cooldown → rejected
        r2 = await executor.execute("speak", {"message": "Second", "zone": "z1"})
        assert r2["success"] is False
        assert "cooldown" in r2["error"].lower()


# ── send_device_command ─────────────────────────────────────────


class TestDeviceCommand:

    @pytest.mark.asyncio
    async def test_device_command_success(self):
        mcp = AsyncMock()
        mcp.call_tool = AsyncMock(return_value={"status": "ok"})

        executor = _make_executor(mcp_bridge=mcp)
        result = await executor.execute(
            "send_device_command",
            {"agent_id": "light_01", "tool_name": "turn_on", "arguments": "{}"},
        )
        assert result["success"] is True
        assert "light_01" in result["result"]

    @pytest.mark.asyncio
    async def test_device_command_json_string_args(self):
        mcp = AsyncMock()
        mcp.call_tool = AsyncMock(return_value={"status": "ok"})

        executor = _make_executor(mcp_bridge=mcp)
        await executor.execute(
            "send_device_command",
            {"agent_id": "light_01", "tool_name": "set_brightness", "arguments": '{"level": 80}'},
        )
        call_args = mcp.call_tool.call_args
        assert call_args[0][2] == {"level": 80}

    @pytest.mark.asyncio
    async def test_device_command_dict_args(self):
        mcp = AsyncMock()
        mcp.call_tool = AsyncMock(return_value={"status": "ok"})

        executor = _make_executor(mcp_bridge=mcp)
        await executor.execute(
            "send_device_command",
            {"agent_id": "light_01", "tool_name": "set_color", "arguments": {"color": "red"}},
        )
        call_args = mcp.call_tool.call_args
        assert call_args[0][2] == {"color": "red"}

    @pytest.mark.asyncio
    async def test_device_command_invalid_json_args(self):
        mcp = AsyncMock()
        mcp.call_tool = AsyncMock(return_value={"status": "ok"})

        executor = _make_executor(mcp_bridge=mcp)
        await executor.execute(
            "send_device_command",
            {"agent_id": "light_01", "tool_name": "x", "arguments": "not-json"},
        )
        call_args = mcp.call_tool.call_args
        assert call_args[0][2] == {}

    @pytest.mark.asyncio
    async def test_device_command_queued_response(self):
        mcp = AsyncMock()
        mcp.call_tool = AsyncMock(return_value={"status": "queued", "target": "leaf_01"})

        executor = _make_executor(mcp_bridge=mcp)
        result = await executor.execute(
            "send_device_command",
            {"agent_id": "swarm_hub_01", "tool_name": "relay_on", "arguments": "{}"},
        )
        assert result["success"] is True
        assert "キュー" in result["result"]

    @pytest.mark.asyncio
    async def test_device_command_adaptive_timeout(self):
        mcp = AsyncMock()
        mcp.call_tool = AsyncMock(return_value={"status": "ok"})
        device_registry = MagicMock()
        device_registry.get_timeout_for_device = MagicMock(return_value=15.0)

        executor = _make_executor(mcp_bridge=mcp, device_registry=device_registry)
        await executor.execute(
            "send_device_command",
            {"agent_id": "light_01", "tool_name": "on"},
        )
        # Verify timeout was passed
        call_kwargs = mcp.call_tool.call_args
        assert call_kwargs.kwargs.get("timeout") == 15.0


# ── get_zone_status ─────────────────────────────────────────────


class TestGetZoneStatus:

    @pytest.mark.asyncio
    async def test_zone_found(self):
        from conftest import make_zone_state, make_mock_world_model

        zone = make_zone_state(
            zone_id="kitchen",
            person_count=2,
            temperature=25.5,
            co2=800,
            humidity=55,
        )
        wm = make_mock_world_model({"kitchen": zone})

        executor = _make_executor(world_model=wm)
        result = await executor.execute("get_zone_status", {"zone_id": "kitchen"})

        assert result["success"] is True
        assert "kitchen" in result["result"]
        assert "25.5" in result["result"]
        assert "800" in result["result"]

    @pytest.mark.asyncio
    async def test_zone_not_found(self):
        wm = MagicMock()
        wm.get_zone = MagicMock(return_value=None)

        executor = _make_executor(world_model=wm)
        result = await executor.execute("get_zone_status", {"zone_id": "nonexistent"})

        assert result["success"] is False
        assert "見つかりません" in result["error"]

    @pytest.mark.asyncio
    async def test_zone_empty(self):
        from conftest import make_zone_state, make_mock_world_model

        zone = make_zone_state(zone_id="lobby", person_count=0)
        wm = make_mock_world_model({"lobby": zone})

        executor = _make_executor(world_model=wm)
        result = await executor.execute("get_zone_status", {"zone_id": "lobby"})
        assert result["success"] is True
        assert "無人" in result["result"]


# ── get_active_tasks ────────────────────────────────────────────


class TestGetActiveTasks:

    @pytest.mark.asyncio
    async def test_no_active_tasks(self):
        dashboard = AsyncMock()
        dashboard.get_active_tasks = AsyncMock(return_value=[])

        executor = _make_executor(dashboard_client=dashboard)
        result = await executor.execute("get_active_tasks", {})

        assert result["success"] is True
        assert "ありません" in result["result"]

    @pytest.mark.asyncio
    async def test_with_active_tasks(self):
        dashboard = AsyncMock()
        dashboard.get_active_tasks = AsyncMock(return_value=[
            {"title": "Clean desk", "is_completed": False, "zone": "main", "task_type": ["cleaning"]},
            {"title": "Refill water", "is_completed": False, "zone": "kitchen", "task_type": []},
        ])

        executor = _make_executor(dashboard_client=dashboard)
        result = await executor.execute("get_active_tasks", {})

        assert result["success"] is True
        assert "2件" in result["result"]
        assert "Clean desk" in result["result"]
        assert "Refill water" in result["result"]

    @pytest.mark.asyncio
    async def test_limits_to_10(self):
        dashboard = AsyncMock()
        tasks = [{"title": f"Task {i}", "is_completed": False, "zone": "main", "task_type": []}
                 for i in range(15)]
        dashboard.get_active_tasks = AsyncMock(return_value=tasks)

        executor = _make_executor(dashboard_client=dashboard)
        result = await executor.execute("get_active_tasks", {})

        assert result["success"] is True
        assert "15件" in result["result"]
        # Only 10 summaries should be listed
        assert result["result"].count("- Task") == 10


# ── get_device_status ───────────────────────────────────────────


class TestGetDeviceStatus:

    @pytest.mark.asyncio
    async def test_device_status_success(self):
        registry = MagicMock()
        registry.get_device_tree = MagicMock(return_value="device tree output")

        executor = _make_executor(device_registry=registry)
        result = await executor.execute("get_device_status", {"zone_id": "main"})

        assert result["success"] is True
        assert result["result"] == "device tree output"

    @pytest.mark.asyncio
    async def test_device_status_no_registry(self):
        executor = _make_executor(device_registry=None)
        result = await executor.execute("get_device_status", {})
        assert result["success"] is False
        assert "DeviceRegistry" in result["error"]

    @pytest.mark.asyncio
    async def test_device_status_all_zones(self):
        registry = MagicMock()
        registry.get_device_tree = MagicMock(return_value="all zones")

        executor = _make_executor(device_registry=registry)
        result = await executor.execute("get_device_status", {})

        assert result["success"] is True
        registry.get_device_tree.assert_called_once_with(zone_id=None)


# ── fetch_acceptance_audio ──────────────────────────────────────


class TestFetchAcceptanceAudio:

    @pytest.mark.asyncio
    async def test_success(self):
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"audio_url": "/audio/acc.mp3"})
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=cm)

        executor = _make_executor(session=session)
        url = await executor.fetch_acceptance_audio()
        assert url == "/audio/acc.mp3"

    @pytest.mark.asyncio
    async def test_failure_returns_none(self):
        resp = AsyncMock()
        resp.status = 404
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=cm)

        executor = _make_executor(session=session)
        url = await executor.fetch_acceptance_audio()
        assert url is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        session = MagicMock()
        session.get = MagicMock(side_effect=Exception("network error"))

        executor = _make_executor(session=session)
        url = await executor.fetch_acceptance_audio()
        assert url is None


# ── Exception handling ──────────────────────────────────────────


class TestExceptionHandling:

    @pytest.mark.asyncio
    async def test_handler_exception_caught(self):
        dashboard = AsyncMock()
        dashboard.create_task = AsyncMock(side_effect=RuntimeError("DB down"))

        executor = _make_executor(dashboard_client=dashboard)
        result = await executor.execute(
            "create_task",
            {"title": "T", "description": "D", "bounty": 500, "urgency": 1},
        )
        assert result["success"] is False
        assert "DB down" in result["error"]
