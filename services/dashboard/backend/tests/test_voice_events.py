"""Unit tests for dashboard voice events router endpoints.

Tests POST /voice-events/ and GET /voice-events/recent.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

# Ensure dashboard/backend is importable
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ.setdefault("JWT_SECRET", "test_jwt_secret_dashboard_32b!!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_service_token_for_unit_tests")

_SERVICE_HEADERS = {"X-Service-Token": os.environ["INTERNAL_SERVICE_TOKEN"]}

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_db


# ── Helpers ─────────────────────────────────────────────────────


def _make_voice_event(
    id=1,
    message="Hello office",
    audio_url="/audio/test.mp3",
    zone="main",
    tone="neutral",
    created_at=None,
):
    class FakeVoiceEvent:
        pass
    ev = FakeVoiceEvent()
    ev.id = id
    ev.message = message
    ev.audio_url = audio_url
    ev.zone = zone
    ev.tone = tone
    ev.created_at = created_at or datetime.now(timezone.utc)
    return ev


class MockScalars:
    def __init__(self, items=None):
        self._items = list(items) if items else []

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return self._items


class MockResult:
    def __init__(self, items=None):
        self._items = list(items) if items else []

    def scalars(self):
        return MockScalars(self._items)

    def scalar(self):
        return self._items[0] if self._items else None


def _make_mock_db(execute_side_effects=None):
    db = AsyncMock()
    if execute_side_effects is not None:
        db.execute.side_effect = [MockResult(items) for items in execute_side_effects]
    else:
        db.execute.return_value = MockResult([])

    async def _refresh(obj):
        if not hasattr(obj, 'id') or obj.id is None:
            obj.id = 1
        if not hasattr(obj, 'created_at') or obj.created_at is None:
            obj.created_at = datetime.now(timezone.utc)
    db.refresh = _refresh

    return db


def _create_app(db_mock):
    from routers.voice_events import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_mock
    return app


# ── POST /voice-events/ ───────────────────────────────────────


class TestCreateVoiceEvent:
    """POST /voice-events/ — record a voice event."""

    def test_create_event_success(self):
        db = _make_mock_db()
        # capture what gets added
        added_objects = []
        original_add = db.add

        def capture_add(obj):
            added_objects.append(obj)
            obj.id = 1
            obj.created_at = datetime.now(timezone.utc)
        db.add = capture_add

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/voice-events/", json={
            "message": "Task available!",
            "audio_url": "/audio/task1.mp3",
            "zone": "main",
            "tone": "caring",
        }, headers=_SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Task available!"
        assert data["audio_url"] == "/audio/task1.mp3"
        assert data["zone"] == "main"
        assert data["tone"] == "caring"
        assert "id" in data
        assert "created_at" in data

    def test_create_event_with_defaults(self):
        """Create event with only required fields (tone defaults to neutral)."""
        db = _make_mock_db()

        def capture_add(obj):
            obj.id = 2
            obj.created_at = datetime.now(timezone.utc)
        db.add = capture_add

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/voice-events/", json={
            "message": "System alert",
            "audio_url": "/audio/alert.mp3",
        }, headers=_SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["tone"] == "neutral"
        assert data["zone"] is None

    def test_create_event_with_humorous_tone(self):
        db = _make_mock_db()

        def capture_add(obj):
            obj.id = 3
            obj.created_at = datetime.now(timezone.utc)
        db.add = capture_add

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/voice-events/", json={
            "message": "Coffee time!",
            "audio_url": "/audio/coffee.mp3",
            "zone": "kitchen",
            "tone": "humorous",
        }, headers=_SERVICE_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["tone"] == "humorous"
        assert resp.json()["zone"] == "kitchen"

    def test_create_event_missing_required_fields(self):
        """Missing message → 422 validation error."""
        db = _make_mock_db()
        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/voice-events/", json={
            "audio_url": "/audio/test.mp3",
        }, headers=_SERVICE_HEADERS)
        assert resp.status_code == 422

    def test_create_event_missing_audio_url(self):
        """Missing audio_url → 422 validation error."""
        db = _make_mock_db()
        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/voice-events/", json={
            "message": "Test",
        }, headers=_SERVICE_HEADERS)
        assert resp.status_code == 422


# ── GET /voice-events/recent ──────────────────────────────────


class TestGetRecentVoiceEvents:
    """GET /voice-events/recent — fetch recent events (60s polling window)."""

    def test_empty_results(self):
        db = _make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/voice-events/recent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_recent_events(self):
        now = datetime.now(timezone.utc)
        e1 = _make_voice_event(id=1, message="Alert 1", created_at=now)
        e2 = _make_voice_event(id=2, message="Alert 2", created_at=now - timedelta(seconds=30))
        db = _make_mock_db([[e1, e2]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/voice-events/recent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["message"] == "Alert 1"
        assert data[1]["message"] == "Alert 2"

    def test_returns_event_with_all_fields(self):
        now = datetime.now(timezone.utc)
        ev = _make_voice_event(
            id=5, message="Testing", audio_url="/audio/t.mp3",
            zone="lab", tone="alert", created_at=now,
        )
        db = _make_mock_db([[ev]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/voice-events/recent")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 5
        assert data[0]["message"] == "Testing"
        assert data[0]["audio_url"] == "/audio/t.mp3"
        assert data[0]["zone"] == "lab"
        assert data[0]["tone"] == "alert"
        assert "created_at" in data[0]

    def test_single_recent_event(self):
        now = datetime.now(timezone.utc)
        ev = _make_voice_event(id=1, created_at=now)
        db = _make_mock_db([[ev]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/voice-events/recent")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
