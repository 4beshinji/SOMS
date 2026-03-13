"""Unit tests for dashboard sensor router endpoints.

Tests GET /sensors/latest, /sensors/time-series, /sensors/zones,
/sensors/events, /sensors/llm-activity, /sensors/llm-timeline.

Uses dependency injection override to mock the SensorDataRepository.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from repositories.deps import get_sensor_repo
from repositories.sensor_repository import (
    SensorDataRepository,
    SensorReading,
    AggregatedReading,
    ZoneSnapshot,
    EventItem,
    LLMActivitySummary,
    LLMTimelinePoint as RepoLLMTimelinePoint,
)


# ── Helpers ─────────────────────────────────────────────────────


NOW = datetime(2026, 2, 21, 12, 0, 0, tzinfo=timezone.utc)


def _create_mock_repo():
    """Create a mock SensorDataRepository with AsyncMock methods."""
    repo = AsyncMock(spec=SensorDataRepository)
    repo.get_latest_readings.return_value = []
    repo.get_time_series.return_value = []
    repo.get_zone_overview.return_value = []
    repo.get_event_feed.return_value = []
    repo.get_llm_activity.return_value = LLMActivitySummary(
        cycles=0, total_tool_calls=0, avg_duration_sec=0.0, hours=24,
    )
    repo.get_llm_timeline.return_value = []
    return repo


def _create_app(repo_mock):
    from routers.sensors import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_sensor_repo] = lambda: repo_mock
    return app


# ── GET /sensors/latest ────────────────────────────────────────


class TestGetLatestReadings:
    """GET /sensors/latest — latest value per zone x channel."""

    def test_empty_results(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/latest")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_readings(self):
        repo = _create_mock_repo()
        repo.get_latest_readings.return_value = [
            SensorReading(
                timestamp=NOW, zone="main", channel="temperature",
                value=25.5, device_id="env_01",
            ),
            SensorReading(
                timestamp=NOW, zone="main", channel="humidity",
                value=60.0, device_id="env_01",
            ),
        ]
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["zone"] == "main"
        assert data[0]["channel"] == "temperature"
        assert data[0]["value"] == 25.5
        assert data[0]["device_id"] == "env_01"

    def test_zone_filter(self):
        """Zone query parameter is passed to repository."""
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/latest?zone=lab")
        assert resp.status_code == 200
        repo.get_latest_readings.assert_called_once_with(zone="lab")

    def test_no_zone_filter(self):
        """Without zone param, None is passed."""
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/latest")
        assert resp.status_code == 200
        repo.get_latest_readings.assert_called_once_with(zone=None)

    def test_reading_without_device_id(self):
        repo = _create_mock_repo()
        repo.get_latest_readings.return_value = [
            SensorReading(
                timestamp=NOW, zone="main", channel="co2",
                value=800.0, device_id=None,
            ),
        ]
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/latest")
        data = resp.json()
        assert data[0]["device_id"] is None


# ── GET /sensors/time-series ───────────────────────────────────


class TestGetTimeSeries:
    """GET /sensors/time-series — chart-ready time series data."""

    def test_empty_results(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/time-series")
        assert resp.status_code == 200
        data = resp.json()
        assert data["points"] == []
        assert data["window"] == "1h"

    def test_returns_aggregated_points(self):
        repo = _create_mock_repo()
        repo.get_time_series.return_value = [
            AggregatedReading(
                period_start=NOW, zone="main", channel="temperature",
                avg=24.0, max=26.0, min=22.0, count=60,
            ),
        ]
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/time-series?zone=main&channel=temperature")
        assert resp.status_code == 200
        data = resp.json()
        assert data["zone"] == "main"
        assert data["channel"] == "temperature"
        assert len(data["points"]) == 1
        pt = data["points"][0]
        assert pt["avg"] == 24.0
        assert pt["max"] == 26.0
        assert pt["min"] == 22.0
        assert pt["count"] == 60

    def test_window_parameter_passed(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/time-series?window=1d")
        assert resp.status_code == 200
        data = resp.json()
        assert data["window"] == "1d"

    def test_limit_parameter(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/time-series?limit=10")
        assert resp.status_code == 200
        # Verify the query was constructed with limit=10
        call_args = repo.get_time_series.call_args[0][0]
        assert call_args.limit == 10

    def test_limit_validation_min(self):
        """Limit < 1 should fail validation."""
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/time-series?limit=0")
        assert resp.status_code == 422

    def test_limit_validation_max(self):
        """Limit > 1000 should fail validation."""
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/time-series?limit=1001")
        assert resp.status_code == 422


# ── GET /sensors/zones ─────────────────────────────────────────


class TestGetZoneOverview:
    """GET /sensors/zones — all-zone overview snapshot."""

    def test_empty_zones(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/zones")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_zone_snapshots(self):
        repo = _create_mock_repo()
        repo.get_zone_overview.return_value = [
            ZoneSnapshot(
                zone="main",
                channels={"temperature": 25.0, "humidity": 60.0},
                event_count=5,
                last_update=NOW,
            ),
            ZoneSnapshot(
                zone="lab",
                channels={"co2": 800.0},
                event_count=2,
                last_update=NOW,
            ),
        ]
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/zones")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["zone"] == "main"
        assert data[0]["channels"]["temperature"] == 25.0
        assert data[0]["event_count"] == 5
        assert data[1]["zone"] == "lab"

    def test_zone_with_no_last_update(self):
        repo = _create_mock_repo()
        repo.get_zone_overview.return_value = [
            ZoneSnapshot(zone="empty", channels={}, event_count=0, last_update=None),
        ]
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/zones")
        data = resp.json()
        assert data[0]["last_update"] is None


# ── GET /sensors/events ────────────────────────────────────────


class TestGetEventFeed:
    """GET /sensors/events — world model event feed."""

    def test_empty_events(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/events")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_events(self):
        repo = _create_mock_repo()
        repo.get_event_feed.return_value = [
            EventItem(
                timestamp=NOW, zone="main", event_type="temperature_alert",
                source_device="env_01", data={"value": 32.0, "threshold": 30.0},
            ),
        ]
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/events")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["zone"] == "main"
        assert data[0]["event_type"] == "temperature_alert"
        assert data[0]["source_device"] == "env_01"
        assert data[0]["data"]["value"] == 32.0

    def test_zone_filter_parameter(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/events?zone=lab")
        assert resp.status_code == 200
        repo.get_event_feed.assert_called_once_with(zone="lab", limit=50)

    def test_limit_parameter(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/events?limit=10")
        assert resp.status_code == 200
        repo.get_event_feed.assert_called_once_with(zone=None, limit=10)

    def test_limit_validation_min(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/events?limit=0")
        assert resp.status_code == 422

    def test_limit_validation_max(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/events?limit=201")
        assert resp.status_code == 422

    def test_event_with_empty_data(self):
        repo = _create_mock_repo()
        repo.get_event_feed.return_value = [
            EventItem(
                timestamp=NOW, zone="main", event_type="heartbeat",
                source_device=None, data={},
            ),
        ]
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/events")
        data = resp.json()
        assert data[0]["source_device"] is None
        assert data[0]["data"] == {}


# ── GET /sensors/llm-activity ──────────────────────────────────


class TestGetLLMActivity:
    """GET /sensors/llm-activity — LLM decision-making summary."""

    def test_default_hours(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/llm-activity")
        assert resp.status_code == 200
        repo.get_llm_activity.assert_called_once_with(hours=24)

    def test_custom_hours(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/llm-activity?hours=48")
        assert resp.status_code == 200
        repo.get_llm_activity.assert_called_once_with(hours=48)

    def test_returns_activity_summary(self):
        repo = _create_mock_repo()
        repo.get_llm_activity.return_value = LLMActivitySummary(
            cycles=100, total_tool_calls=250, avg_duration_sec=2.5, hours=24,
        )
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/llm-activity")
        data = resp.json()
        assert data["cycles"] == 100
        assert data["total_tool_calls"] == 250
        assert data["avg_duration_sec"] == 2.5
        assert data["hours"] == 24

    def test_zero_activity(self):
        repo = _create_mock_repo()
        repo.get_llm_activity.return_value = LLMActivitySummary(
            cycles=0, total_tool_calls=0, avg_duration_sec=0.0, hours=24,
        )
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/llm-activity")
        data = resp.json()
        assert data["cycles"] == 0
        assert data["total_tool_calls"] == 0

    def test_hours_validation_min(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/llm-activity?hours=0")
        assert resp.status_code == 422

    def test_hours_validation_max(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/llm-activity?hours=721")
        assert resp.status_code == 422


# ── GET /sensors/llm-timeline ──────────────────────────────────


class TestGetLLMTimeline:
    """GET /sensors/llm-timeline — hourly-bucketed LLM timeline."""

    def test_empty_timeline(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/llm-timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hours"] == 24
        assert data["points"] == []

    def test_returns_timeline_points(self):
        repo = _create_mock_repo()
        repo.get_llm_timeline.return_value = [
            RepoLLMTimelinePoint(
                timestamp=NOW, cycles=10, tool_calls=25, avg_duration_sec=1.5,
            ),
            RepoLLMTimelinePoint(
                timestamp=NOW, cycles=8, tool_calls=20, avg_duration_sec=2.0,
            ),
        ]
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/llm-timeline")
        data = resp.json()
        assert len(data["points"]) == 2
        assert data["points"][0]["cycles"] == 10
        assert data["points"][0]["tool_calls"] == 25
        assert data["points"][1]["avg_duration_sec"] == 2.0

    def test_custom_hours(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/llm-timeline?hours=48")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hours"] == 48
        repo.get_llm_timeline.assert_called_once_with(hours=48)

    def test_hours_validation_min(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/llm-timeline?hours=0")
        assert resp.status_code == 422

    def test_hours_validation_max(self):
        repo = _create_mock_repo()
        app = _create_app(repo)
        client = TestClient(app)
        resp = client.get("/sensors/llm-timeline?hours=721")
        assert resp.status_code == 422
