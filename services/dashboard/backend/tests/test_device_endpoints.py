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
    orientation_deg=None,
    fov_deg=None,
    detection_range_m=None,
    label=None,
    context=None,
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
    dp.orientation_deg = orientation_deg
    dp.fov_deg = fov_deg
    dp.detection_range_m = detection_range_m
    dp.label = label
    dp.context = context
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


# ── device_id Validation ──────────────────────────────────────


class TestDeviceIdValidation:
    """POST /devices/positions/ — device_id format validation."""

    def test_valid_device_id(self):
        """Lowercase alphanumeric + underscore → 201."""
        db = make_mock_db([
            MockResult([], scalar_value=None),
        ])
        db.add = lambda obj: setattr(obj, 'id', 1)
        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/positions/", json={
            "device_id": "env_01",
            "zone": "main",
            "x": 1.0,
            "y": 2.0,
        }, headers=auth_header())
        assert resp.status_code == 201

    def test_invalid_device_id_uppercase(self):
        """Uppercase letters → 422."""
        db = make_mock_db()
        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/positions/", json={
            "device_id": "Env_01",
            "zone": "main",
            "x": 1.0,
            "y": 2.0,
        }, headers=auth_header())
        assert resp.status_code == 422

    def test_invalid_device_id_spaces(self):
        """Spaces → 422."""
        db = make_mock_db()
        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/positions/", json={
            "device_id": "env 01",
            "zone": "main",
            "x": 1.0,
            "y": 2.0,
        }, headers=auth_header())
        assert resp.status_code == 422

    def test_invalid_device_id_special_chars(self):
        """Special characters → 422."""
        db = make_mock_db()
        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/positions/", json={
            "device_id": "dev-01!",
            "zone": "main",
            "x": 1.0,
            "y": 2.0,
        }, headers=auth_header())
        assert resp.status_code == 422

    def test_invalid_device_id_empty(self):
        """Empty string → 422."""
        db = make_mock_db()
        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/devices/positions/", json={
            "device_id": "",
            "zone": "main",
            "x": 1.0,
            "y": 2.0,
        }, headers=auth_header())
        assert resp.status_code == 422


# ── GET /devices/discovery ────────────────────────────────────


class _RowsResult:
    """Mocks a SQLAlchemy result that supports .all() returning raw tuples."""
    def __init__(self, rows=None):
        self._rows = list(rows) if rows else []
    def all(self):
        return self._rows
    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class TestDiscoveryEndpoint:
    """GET /devices/discovery — merged device discovery."""

    def test_discovery_empty(self):
        """No config, no snapshot, no placed → empty list."""
        from unittest.mock import patch, AsyncMock
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _RowsResult(),   # snapshot query → None
            _RowsResult(),   # placed device_ids → empty
        ])
        app = _create_app(db)
        client = TestClient(app)
        with patch("routers.devices._load_bridge_configs", return_value=[]):
            resp = client.get("/devices/discovery")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_discovery_from_config(self):
        """Bridge config devices show up with source=config."""
        from unittest.mock import patch, AsyncMock
        config_devs = [
            {"device_id": "z2m_presence_01", "device_type": "presence", "zone": "main",
             "label": "Test", "channels": ["motion"], "bridge": "zigbee2mqtt"},
        ]
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _RowsResult(),   # no snapshot
            _RowsResult(),   # no placed
        ])
        app = _create_app(db)
        client = TestClient(app)
        with patch("routers.devices._load_bridge_configs", return_value=config_devs):
            resp = client.get("/devices/discovery")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["device_id"] == "z2m_presence_01"
        assert data[0]["source"] == "config"
        assert data[0]["placed"] is False
        assert data[0]["bridge"] == "zigbee2mqtt"

    def test_discovery_placed_flag(self):
        """Devices already in device_positions get placed=True."""
        from unittest.mock import patch, AsyncMock
        config_devs = [
            {"device_id": "z2m_presence_01", "device_type": "presence", "zone": "main",
             "label": None, "channels": ["motion"], "bridge": "zigbee2mqtt"},
        ]
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _RowsResult(),                                  # no snapshot
            _RowsResult([("z2m_presence_01",)]),            # placed IDs
        ])
        app = _create_app(db)
        client = TestClient(app)
        with patch("routers.devices._load_bridge_configs", return_value=config_devs):
            resp = client.get("/devices/discovery")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["placed"] is True
