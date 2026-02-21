"""Shared fixtures and helpers for brain service unit tests."""
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_THIS_DIR = str(Path(__file__).resolve().parent)
BRAIN_SRC = str(Path(__file__).resolve().parent.parent / "src")

# Add source directories to sys.path for imports
if BRAIN_SRC not in sys.path:
    sys.path.insert(0, BRAIN_SRC)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# Set test-safe environment BEFORE importing any brain modules
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("MQTT_PORT", "1883")
os.environ.setdefault("MQTT_USER", "test")
os.environ.setdefault("MQTT_PASS", "test")
os.environ.setdefault("LLM_API_URL", "http://localhost:8001/v1")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("DASHBOARD_API_URL", "http://localhost:8000")


# ── Mock helpers ─────────────────────────────────────────────────


def make_zone_state(
    zone_id="main",
    person_count=0,
    dominant_activity="unknown",
    temperature=None,
    co2=None,
    humidity=None,
):
    """Create a mock ZoneState with configurable fields."""
    from world_model.data_classes import (
        ZoneState,
        EnvironmentData,
        OccupancyData,
    )

    occupancy = OccupancyData(
        person_count=person_count,
        vision_count=person_count,
        activity_distribution={"active": person_count} if dominant_activity == "active"
        else {"focused": person_count} if dominant_activity == "focused"
        else {},
    )
    environment = EnvironmentData(
        temperature=temperature,
        co2=co2,
        humidity=humidity,
    )
    return ZoneState(
        zone_id=zone_id,
        environment=environment,
        occupancy=occupancy,
    )


def make_mock_world_model(zones=None):
    """Create a mock WorldModel with configurable zones.

    Args:
        zones: dict mapping zone_id -> ZoneState (or None for empty)
    """
    wm = MagicMock()
    zones = zones or {}

    def get_zone(zone_id):
        return zones.get(zone_id)

    wm.get_zone = MagicMock(side_effect=get_zone)
    return wm


def make_mock_dashboard_client():
    """Create a mock DashboardClient."""
    client = MagicMock()
    client.api_url = "http://localhost:8000"
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_session.put = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_response),
        __aexit__=AsyncMock(return_value=False),
    ))
    client._get_session = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_session),
        __aexit__=AsyncMock(return_value=False),
    ))
    return client
