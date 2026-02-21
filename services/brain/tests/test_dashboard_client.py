"""Unit tests for DashboardClient — REST API client for the dashboard backend.

Tests verify:
- Task creation with voice generation
- Task listing and filtering
- Task statistics retrieval
- Dual voice generation
- Session management (shared vs ephemeral)
- Error handling for API failures
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dashboard_client import DashboardClient


# ── Helpers ─────────────────────────────────────────────────────


def _mock_response(status=200, json_data=None, text=""):
    """Create a mock aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.text = AsyncMock(return_value=text)
    return resp


def _mock_session(responses=None):
    """Create a mock aiohttp ClientSession with configurable responses.

    Args:
        responses: list of mock responses for sequential calls.
                   If None, returns a 200 response with empty dict.
    """
    if responses is None:
        responses = [_mock_response()]

    call_count = {"n": 0}

    def make_cm(*args, **kwargs):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        resp = responses[idx]
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    session = MagicMock()
    session.post = MagicMock(side_effect=make_cm)
    session.get = MagicMock(side_effect=make_cm)
    return session


# ── Initialization ──────────────────────────────────────────────


class TestInit:

    def test_defaults(self):
        client = DashboardClient()
        # api_url comes from DASHBOARD_API_URL env var or default
        assert client.api_url is not None
        assert client.voice_url is not None
        assert client.enable_voice is True

    def test_custom_urls(self):
        client = DashboardClient(
            api_url="http://custom:9000",
            voice_url="http://voice:9001",
            enable_voice=False,
        )
        assert client.api_url == "http://custom:9000"
        assert client.voice_url == "http://voice:9001"
        assert client.enable_voice is False


# ── create_task ─────────────────────────────────────────────────


class TestCreateTask:

    @pytest.mark.asyncio
    async def test_create_task_success_no_voice(self):
        session = _mock_session([_mock_response(200, {"id": 42, "title": "Test"})])
        client = DashboardClient(enable_voice=False, session=session)

        result = await client.create_task(
            title="Test task",
            description="Test description",
            bounty=1000,
            urgency=2,
            zone="main",
        )

        assert result is not None
        assert result["id"] == 42
        session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_task_with_voice(self):
        voice_resp = _mock_response(200, {
            "announcement_audio_url": "/audio/ann.mp3",
            "announcement_text": "Announcement",
            "completion_audio_url": "/audio/comp.mp3",
            "completion_text": "Complete",
        })
        task_resp = _mock_response(200, {"id": 10})
        session = _mock_session([voice_resp, task_resp])
        client = DashboardClient(enable_voice=True, session=session)

        result = await client.create_task(
            title="Voice task",
            description="Desc",
            bounty=500,
            urgency=1,
            zone="kitchen",
        )

        assert result is not None
        # Should have called post twice (voice + task creation)
        assert session.post.call_count == 2

    @pytest.mark.asyncio
    async def test_create_task_api_failure(self):
        session = _mock_session([_mock_response(500, text="Internal error")])
        client = DashboardClient(enable_voice=False, session=session)

        result = await client.create_task(title="Fail", description="D")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_task_network_error(self):
        session = MagicMock()
        session.post = MagicMock(side_effect=Exception("Connection refused"))
        # Must wrap in context manager
        client = DashboardClient(enable_voice=False, session=session)
        client._session = session

        result = await client.create_task(title="Fail", description="D")
        assert result is None

    @pytest.mark.asyncio
    async def test_task_types_default(self):
        session = _mock_session([_mock_response(200, {"id": 1})])
        client = DashboardClient(enable_voice=False, session=session)

        await client.create_task(title="T", description="D")
        call_args = session.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["task_type"] == ["general"]

    @pytest.mark.asyncio
    async def test_environment_task_type_expiry(self):
        session = _mock_session([_mock_response(200, {"id": 1})])
        client = DashboardClient(enable_voice=False, session=session)

        await client.create_task(
            title="T", description="D", task_types=["environment"]
        )
        call_args = session.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        # Environment tasks should expire sooner (1 hour max)
        expires_at = datetime.fromisoformat(payload["expires_at"])
        now = datetime.now(timezone.utc)
        delta = (expires_at - now).total_seconds()
        assert delta <= 3600 + 60  # 1 hour + small buffer

    @pytest.mark.asyncio
    async def test_supply_task_type_expiry(self):
        session = _mock_session([_mock_response(200, {"id": 1})])
        client = DashboardClient(enable_voice=False, session=session)

        await client.create_task(
            title="T", description="D", task_types=["supply"]
        )
        call_args = session.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        expires_at = datetime.fromisoformat(payload["expires_at"])
        now = datetime.now(timezone.utc)
        delta = (expires_at - now).total_seconds()
        # Supply tasks: 1 week
        assert delta > 86400  # More than 1 day

    @pytest.mark.asyncio
    async def test_voice_failure_non_fatal(self):
        """Voice generation failure should not prevent task creation."""
        voice_resp = _mock_response(500)
        task_resp = _mock_response(200, {"id": 7})
        session = _mock_session([voice_resp, task_resp])
        client = DashboardClient(enable_voice=True, session=session)

        result = await client.create_task(title="T", description="D", bounty=100)
        assert result is not None
        assert result["id"] == 7


# ── get_active_tasks ────────────────────────────────────────────


class TestGetActiveTasks:

    @pytest.mark.asyncio
    async def test_returns_active_only(self):
        tasks = [
            {"title": "Active", "is_completed": False},
            {"title": "Done", "is_completed": True},
            {"title": "Also active", "is_completed": False},
        ]
        session = _mock_session([_mock_response(200, tasks)])
        client = DashboardClient(session=session)

        result = await client.get_active_tasks()
        assert len(result) == 2
        assert all(not t["is_completed"] for t in result)

    @pytest.mark.asyncio
    async def test_api_failure_returns_empty(self):
        session = _mock_session([_mock_response(500)])
        client = DashboardClient(session=session)

        result = await client.get_active_tasks()
        assert result == []

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self):
        session = MagicMock()
        session.get = MagicMock(side_effect=Exception("timeout"))
        client = DashboardClient(session=session)
        client._session = session

        result = await client.get_active_tasks()
        assert result == []


# ── get_task_stats ──────────────────────────────────────────────


class TestGetTaskStats:

    @pytest.mark.asyncio
    async def test_success(self):
        stats = {"active": 5, "completed": 10, "total_xp": 1500}
        session = _mock_session([_mock_response(200, stats)])
        client = DashboardClient(session=session)

        result = await client.get_task_stats()
        assert result == stats

    @pytest.mark.asyncio
    async def test_failure_returns_empty(self):
        session = _mock_session([_mock_response(404)])
        client = DashboardClient(session=session)

        result = await client.get_task_stats()
        assert result == {}


# ── _generate_dual_voice ────────────────────────────────────────


class TestDualVoice:

    @pytest.mark.asyncio
    async def test_success(self):
        voice_data = {
            "announcement_audio_url": "/audio/ann.mp3",
            "announcement_text": "Please clean",
            "completion_audio_url": "/audio/comp.mp3",
            "completion_text": "Thank you",
        }
        session = _mock_session([_mock_response(200, voice_data)])
        client = DashboardClient(session=session)

        result = await client._generate_dual_voice({"title": "Clean"})
        assert result is not None
        assert result["announcement_audio_url"] == "/audio/ann.mp3"

    @pytest.mark.asyncio
    async def test_failure_returns_none(self):
        session = _mock_session([_mock_response(503)])
        client = DashboardClient(session=session)

        result = await client._generate_dual_voice({"title": "Fail"})
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        session = MagicMock()
        session.post = MagicMock(side_effect=Exception("timeout"))
        client = DashboardClient(session=session)
        client._session = session

        result = await client._generate_dual_voice({"title": "Error"})
        assert result is None
