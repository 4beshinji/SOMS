"""Unit tests for dashboard device position router endpoints.

Tests GET /devices/positions/, POST /devices/positions/,
PUT /devices/positions/{device_id}, DELETE /devices/positions/{device_id}.
"""
import json
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_db
from conftest import MockResult, make_mock_db, auth_header


# ── Helpers ─────────────────────────────────────────────────────


def _make_device_position(
    id=1,
    device_id="env_01",
    zone="main",
    x=100.0,
    y=200.0,
    device_type="sensor",
    channels=None,
):
    class FakeDevicePosition:
        pass
    dp = FakeDevicePosition()
    dp.id = id
    dp.device_id = device_id
    dp.zone = zone
    dp.x = x
    dp.y = y
    dp.device_type = device_type
    dp.channels = json.dumps(channels) if channels is not None else "[]"
    dp.created_at = datetime.now(timezone.utc)
    dp.updated_at = None
    return dp


def _create_app(db_mock):
    from routers.devices import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_mock
    return app


# ── GET /devices/positions/ ───────────────────────────────────


class TestListDevicePositions:
    """GET /devices/positions/ — list all device positions."""

    def test_empty_list(self):
        db = make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/devices/positions/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_positions(self):
        dp1 = _make_device_position(id=1, device_id="env_01", zone="main", x=10.0, y=20.0)
        dp2 = _make_device_position(id=2, device_id="cam_01", zone="lab", x=50.0, y=60.0,
                                     device_type="camera", channels=["video"])
        db = make_mock_db([[dp1, dp2]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/devices/positions/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["device_id"] == "env_01"
        assert data[0]["zone"] == "main"
        assert data[0]["x"] == 10.0
        assert data[0]["y"] == 20.0
        assert data[0]["device_type"] == "sensor"
        assert data[0]["channels"] == []
        assert data[1]["device_id"] == "cam_01"
        assert data[1]["channels"] == ["video"]

    def test_channels_parsed_from_json(self):
        dp = _make_device_position(id=1, channels=["temperature", "humidity"])
        db = make_mock_db([[dp]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/devices/positions/")
        data = resp.json()
        assert data[0]["channels"] == ["temperature", "humidity"]

    def test_invalid_channels_json_becomes_empty_list(self):
        dp = _make_device_position(id=1)
        dp.channels = "not-valid-json"
        db = make_mock_db([[dp]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/devices/positions/")
        data = resp.json()
        assert data[0]["channels"] == []

    def test_null_channels_becomes_empty_list(self):
        dp = _make_device_position(id=1)
        dp.channels = None
        db = make_mock_db([[dp]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/devices/positions/")
        data = resp.json()
        assert data[0]["channels"] == []

    def test_null_device_type_defaults_to_sensor(self):
        dp = _make_device_position(id=1)
        dp.device_type = None
        db = make_mock_db([[dp]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/devices/positions/")
        data = resp.json()
        assert data[0]["device_type"] == "sensor"


# ── POST /devices/positions/ ──────────────────────────────────


class TestCreateDevicePosition:
    """POST /devices/positions/ — place a new device."""

    def test_create_success(self):
        # First execute: check duplicate (no result), second: implicit from commit
        db = make_mock_db([
            MockResult([], scalar_value=None),  # duplicate check → None
        ])

        def capture_add(obj):
            obj.id = 1
        db.add = capture_add

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/positions/", json={
            "device_id": "env_01",
            "zone": "main",
            "x": 100.0,
            "y": 200.0,
            "device_type": "sensor",
            "channels": ["temperature", "humidity"],
        }, headers=auth_header())
        assert resp.status_code == 201
        data = resp.json()
        assert data["device_id"] == "env_01"
        assert data["zone"] == "main"
        assert data["x"] == 100.0
        assert data["y"] == 200.0
        assert data["channels"] == ["temperature", "humidity"]

    def test_create_with_defaults(self):
        """Create with minimal fields (device_type defaults to sensor)."""
        db = make_mock_db([
            MockResult([], scalar_value=None),
        ])
        db.add = lambda obj: setattr(obj, 'id', 2)

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/positions/", json={
            "device_id": "cam_01",
            "zone": "lab",
            "x": 50.0,
            "y": 60.0,
        }, headers=auth_header())
        assert resp.status_code == 201
        data = resp.json()
        assert data["device_type"] == "sensor"  # default
        assert data["channels"] == []  # default

    def test_create_duplicate_device_id_returns_409(self):
        """Duplicate device_id → 409 Conflict."""
        existing = _make_device_position(id=1, device_id="env_01")
        db = make_mock_db([
            MockResult([], scalar_value=existing),  # duplicate found
        ])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/positions/", json={
            "device_id": "env_01",
            "zone": "main",
            "x": 100.0,
            "y": 200.0,
        }, headers=auth_header())
        assert resp.status_code == 409
        assert "already placed" in resp.json()["detail"]

    def test_create_missing_required_fields(self):
        """Missing device_id → 422."""
        db = make_mock_db()
        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/positions/", json={
            "zone": "main",
            "x": 100.0,
            "y": 200.0,
        }, headers=auth_header())
        assert resp.status_code == 422

    def test_create_missing_coordinates(self):
        """Missing x or y → 422."""
        db = make_mock_db()
        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/positions/", json={
            "device_id": "env_01",
            "zone": "main",
        }, headers=auth_header())
        assert resp.status_code == 422


# ── PUT /devices/positions/{device_id} ────────────────────────


class TestUpdateDevicePosition:
    """PUT /devices/positions/{device_id} — update device position."""

    def test_update_success(self):
        dp = _make_device_position(id=1, device_id="env_01", x=10.0, y=20.0)
        db = make_mock_db([
            MockResult([], scalar_value=dp),  # find device
        ])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/devices/positions/env_01", json={
            "x": 150.0,
            "y": 250.0,
        }, headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["x"] == 150.0
        assert data["y"] == 250.0
        assert dp.x == 150.0
        assert dp.y == 250.0

    def test_update_with_zone(self):
        dp = _make_device_position(id=1, device_id="env_01", zone="main")
        db = make_mock_db([
            MockResult([], scalar_value=dp),
        ])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/devices/positions/env_01", json={
            "x": 100.0,
            "y": 200.0,
            "zone": "lab",
        }, headers=auth_header())
        assert resp.status_code == 200
        assert dp.zone == "lab"

    def test_update_without_zone_keeps_original(self):
        """When zone is not provided, original zone is preserved."""
        dp = _make_device_position(id=1, device_id="env_01", zone="main")
        db = make_mock_db([
            MockResult([], scalar_value=dp),
        ])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/devices/positions/env_01", json={
            "x": 100.0,
            "y": 200.0,
        }, headers=auth_header())
        assert resp.status_code == 200
        assert dp.zone == "main"  # unchanged

    def test_update_not_found(self):
        db = make_mock_db([
            MockResult([], scalar_value=None),
        ])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/devices/positions/nonexistent", json={
            "x": 100.0,
            "y": 200.0,
        }, headers=auth_header())
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_update_missing_coordinates(self):
        """Missing x or y → 422."""
        db = make_mock_db()
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/devices/positions/env_01", json={
            "x": 100.0,
        }, headers=auth_header())
        assert resp.status_code == 422


# ── DELETE /devices/positions/{device_id} ─────────────────────


class TestDeleteDevicePosition:
    """DELETE /devices/positions/{device_id} — remove device from floor plan."""

    def test_delete_success(self):
        dp = _make_device_position(id=1, device_id="env_01")
        db = make_mock_db([
            MockResult([], scalar_value=dp),   # find device
            MockResult([]),                     # delete execute
        ])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.delete("/devices/positions/env_01", headers=auth_header())
        assert resp.status_code == 204

    def test_delete_not_found(self):
        db = make_mock_db([
            MockResult([], scalar_value=None),
        ])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.delete("/devices/positions/nonexistent", headers=auth_header())
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_delete_returns_no_content(self):
        """Successful delete returns 204 with no body."""
        dp = _make_device_position(id=1, device_id="cam_01")
        db = make_mock_db([
            MockResult([], scalar_value=dp),
            MockResult([]),
        ])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.delete("/devices/positions/cam_01", headers=auth_header())
        assert resp.status_code == 204
        assert resp.content == b""
