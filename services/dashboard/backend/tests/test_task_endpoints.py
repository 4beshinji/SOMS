"""Unit tests for dashboard task router endpoints.

Tests GET /tasks/, POST /tasks/, PUT /tasks/{id}/reminded,
GET /tasks/queue, PUT /tasks/{id}/dispatch, GET /tasks/stats.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

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


def _make_task_obj(
    id=1,
    title="Test Task",
    description="A task description",
    location="Office",
    bounty_gold=1000,
    bounty_xp=50,
    is_completed=False,
    is_queued=False,
    task_type=None,
    urgency=2,
    zone="main",
    min_people_required=1,
    estimated_duration=10,
    assigned_to=None,
    accepted_at=None,
    dispatched_at=None,
    expires_at=None,
    last_reminded_at=None,
    report_status=None,
    completion_note=None,
    region_id="local",
):
    now = datetime.now(timezone.utc)

    class FakeTask:
        def __init__(self):
            # Provide __dict__ iteration for t_dict construction
            pass
    task = FakeTask()
    task.id = id
    task.title = title
    task.description = description
    task.location = location
    task.bounty_gold = bounty_gold
    task.bounty_xp = bounty_xp
    task.is_completed = is_completed
    task.is_queued = is_queued
    task.created_at = now
    task.completed_at = None
    task.dispatched_at = dispatched_at or now
    task.expires_at = expires_at
    task.task_type = json.dumps(task_type) if task_type else None
    task.urgency = urgency
    task.zone = zone
    task.min_people_required = min_people_required
    task.estimated_duration = estimated_duration
    task.announcement_audio_url = None
    task.announcement_text = None
    task.completion_audio_url = None
    task.completion_text = None
    task.assigned_to = assigned_to
    task.accepted_at = accepted_at
    task.last_reminded_at = last_reminded_at
    task.report_status = report_status
    task.completion_note = completion_note
    task.region_id = region_id
    return task


def _make_sys_stats(total_xp=0, tasks_completed=0, tasks_created=0):
    class FakeStats:
        pass
    s = FakeStats()
    s.id = 1
    s.total_xp = total_xp
    s.tasks_completed = tasks_completed
    s.tasks_created = tasks_created
    return s


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

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None


def _make_mock_db(execute_side_effects=None):
    db = AsyncMock()
    if execute_side_effects is not None:
        db.execute.side_effect = [MockResult(items) for items in execute_side_effects]
    else:
        db.execute.return_value = MockResult([])

    async def _refresh(obj):
        if hasattr(obj, 'accepted_at') and obj.accepted_at is not None and not isinstance(obj.accepted_at, datetime):
            obj.accepted_at = datetime.now(timezone.utc)
        if hasattr(obj, 'completed_at') and obj.completed_at is not None and not isinstance(obj.completed_at, datetime):
            obj.completed_at = datetime.now(timezone.utc)
        if hasattr(obj, 'dispatched_at') and obj.dispatched_at is not None and not isinstance(obj.dispatched_at, datetime):
            obj.dispatched_at = datetime.now(timezone.utc)
        if hasattr(obj, 'last_reminded_at') and obj.last_reminded_at is not None and not isinstance(obj.last_reminded_at, datetime):
            obj.last_reminded_at = datetime.now(timezone.utc)

    db.refresh = _refresh
    return db


def _new_task_refresh(obj, default_id=1):
    """Simulate refresh on a newly-created models.Task by setting SQLAlchemy defaults."""
    if not hasattr(obj, 'id') or obj.id is None:
        obj.id = default_id
    if hasattr(obj, 'created_at') and obj.created_at is None:
        obj.created_at = datetime.now(timezone.utc)
    if hasattr(obj, 'dispatched_at') and obj.dispatched_at is not None and not isinstance(obj.dispatched_at, datetime):
        obj.dispatched_at = datetime.now(timezone.utc)
    # Simulate SQLAlchemy column defaults
    if getattr(obj, 'is_completed', None) is None:
        obj.is_completed = False
    if getattr(obj, 'is_queued', None) is None:
        obj.is_queued = False
    if getattr(obj, 'bounty_xp', None) is None:
        obj.bounty_xp = 50
    if getattr(obj, 'last_reminded_at', None) is None:
        obj.last_reminded_at = None
    if getattr(obj, 'accepted_at', None) is None:
        obj.accepted_at = None
    if getattr(obj, 'assigned_to', None) is None:
        obj.assigned_to = None
    if getattr(obj, 'report_status', None) is None:
        obj.report_status = None
    if getattr(obj, 'completion_note', None) is None:
        obj.completion_note = None
    if getattr(obj, 'completed_at', None) is None:
        obj.completed_at = None


def _create_app(db_mock):
    from routers.tasks import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_mock
    return app


# ── GET /tasks/ ────────────────────────────────────────────────


class TestReadTasks:
    """GET /tasks/ — list tasks with expiration filtering."""

    def test_returns_empty_list(self):
        db = _make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_single_task(self):
        task = _make_task_obj(id=1, title="Fix AC")
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert data[0]["title"] == "Fix AC"

    def test_returns_multiple_tasks(self):
        t1 = _make_task_obj(id=1, title="Task A")
        t2 = _make_task_obj(id=2, title="Task B")
        db = _make_mock_db([[t1, t2]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_pagination_skip_limit(self):
        """Pagination params are accepted (actual filtering in DB)."""
        task = _make_task_obj(id=5)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/?skip=10&limit=5")
        assert resp.status_code == 200

    def test_task_type_parsed_from_json(self):
        """task_type stored as JSON string should be parsed to a list."""
        task = _make_task_obj(id=1, task_type=["cleaning", "maintenance"])
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        data = resp.json()
        assert data[0]["task_type"] == ["cleaning", "maintenance"]

    def test_null_task_type_becomes_empty_list(self):
        """task_type=None in DB should become [] in response."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        data = resp.json()
        assert data[0]["task_type"] == []

    def test_invalid_json_task_type_becomes_empty_list(self):
        """Invalid JSON in task_type should gracefully become []."""
        task = _make_task_obj(id=1)
        task.task_type = "not-valid-json"
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        data = resp.json()
        assert data[0]["task_type"] == []

    def test_task_fields_in_response(self):
        """Verify key fields are present in response."""
        task = _make_task_obj(
            id=42, title="Water Plants", description="All zones",
            location="Lab", bounty_gold=500, urgency=3, zone="lab",
            region_id="tokyo",
        )
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        data = resp.json()[0]
        assert data["id"] == 42
        assert data["title"] == "Water Plants"
        assert data["description"] == "All zones"
        assert data["location"] == "Lab"
        assert data["bounty_gold"] == 500
        assert data["urgency"] == 3
        assert data["zone"] == "lab"
        assert data["region_id"] == "tokyo"
        assert data["is_completed"] is False
        assert data["is_queued"] is False


# ── POST /tasks/ ───────────────────────────────────────────────


class TestCreateTask:
    """POST /tasks/ — create task with duplicate detection."""

    def test_create_new_task(self):
        """No duplicate found → create new task."""
        sys_stats = _make_sys_stats()
        # execute calls: Stage 1 query (no dup), Stage 2 skipped (no zone+task_type), sys_stats query, final result
        db = _make_mock_db([
            [],            # Stage 1: no duplicate
            [sys_stats],   # _get_or_create_system_stats
        ])

        # After commit + refresh, the db.add'd object gets used
        db.add = lambda obj: None

        async def _refresh(obj):
            _new_task_refresh(obj, default_id=10)
        db.refresh = _refresh

        with patch("routers.tasks._grant_device_xp", new_callable=AsyncMock):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.post("/tasks/", json={
                "title": "New Task",
                "description": "Do something",
                "location": "Room A",
                "bounty_gold": 1000,
                "zone": "main",
            }, headers=_SERVICE_HEADERS)
        assert resp.status_code == 200
        assert sys_stats.tasks_created == 1

    def test_duplicate_stage1_exact_title_location(self):
        """Stage 1: exact title+location match → updates existing task."""
        existing = _make_task_obj(id=5, title="Fix Light", location="Room A")
        db = _make_mock_db([
            [existing],   # Stage 1 finds duplicate
        ])

        async def _refresh(obj):
            pass
        db.refresh = _refresh

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/tasks/", json={
            "title": "Fix Light",
            "description": "Updated description",
            "location": "Room A",
            "bounty_gold": 2000,
        }, headers=_SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 5  # Same task ID
        assert existing.description == "Updated description"
        assert existing.bounty_gold == 2000

    def test_duplicate_stage2_zone_task_type_overlap(self):
        """Stage 2: same zone + overlapping task_type → updates existing."""
        existing = _make_task_obj(id=7, title="Old Title", zone="main",
                                  task_type=["cleaning", "hvac"])
        db = _make_mock_db([
            [],            # Stage 1: no exact match
            [existing],    # Stage 2: zone candidates
        ])

        async def _refresh(obj):
            pass
        db.refresh = _refresh

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/tasks/", json={
            "title": "Different Title",
            "description": "New desc",
            "zone": "main",
            "task_type": ["cleaning"],
        }, headers=_SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 7  # Same existing task updated

    def test_no_duplicate_stage2_no_overlap(self):
        """Stage 2: same zone but different task_type → creates new."""
        existing = _make_task_obj(id=7, title="Old Title", zone="main",
                                  task_type=["hvac"])
        sys_stats = _make_sys_stats()
        db = _make_mock_db([
            [],            # Stage 1: no exact match
            [existing],    # Stage 2: zone candidates (but no overlap)
            [sys_stats],   # _get_or_create_system_stats
        ])

        db.add = lambda obj: None

        async def _refresh(obj):
            _new_task_refresh(obj, default_id=20)
        db.refresh = _refresh

        with patch("routers.tasks._grant_device_xp", new_callable=AsyncMock):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.post("/tasks/", json={
                "title": "Different Title",
                "description": "New",
                "zone": "main",
                "task_type": ["cleaning"],  # No overlap with "hvac"
            }, headers=_SERVICE_HEADERS)
        assert resp.status_code == 200

    def test_duplicate_updates_voice_data_when_provided(self):
        """When updating a duplicate, voice data is only updated if provided."""
        existing = _make_task_obj(id=5, title="Fix Light", location="Room A")
        existing.announcement_audio_url = "/audio/old.mp3"
        existing.announcement_text = "Old text"
        db = _make_mock_db([[existing]])

        async def _refresh(obj):
            pass
        db.refresh = _refresh

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/tasks/", json={
            "title": "Fix Light",
            "location": "Room A",
            "announcement_audio_url": "/audio/new.mp3",
        }, headers=_SERVICE_HEADERS)
        assert resp.status_code == 200
        assert existing.announcement_audio_url == "/audio/new.mp3"
        # Text not provided, should keep old value
        assert existing.announcement_text == "Old text"

    def test_create_task_with_minimal_fields(self):
        """Create with just title (all others default)."""
        sys_stats = _make_sys_stats()
        db = _make_mock_db([
            [],            # Stage 1: no dup
            [sys_stats],   # sys_stats
        ])
        db.add = lambda obj: None

        async def _refresh(obj):
            _new_task_refresh(obj, default_id=1)
        db.refresh = _refresh

        with patch("routers.tasks._grant_device_xp", new_callable=AsyncMock):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.post("/tasks/", json={"title": "Simple Task"}, headers=_SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Simple Task"
        assert data["bounty_gold"] == 10  # default
        assert data["urgency"] == 2       # default


# ── PUT /tasks/{id}/reminded ───────────────────────────────────


class TestMarkTaskReminded:
    """PUT /tasks/{task_id}/reminded — update last_reminded_at."""

    def test_success(self):
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/1/reminded", headers=_SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        # last_reminded_at should be set (func.now() resolved by refresh mock)
        assert data["last_reminded_at"] is not None

    def test_not_found(self):
        db = _make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/999/reminded", headers=_SERVICE_HEADERS)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_reminded_returns_full_task(self):
        """Response should contain all task fields."""
        task = _make_task_obj(id=3, title="Check AC", zone="lab", bounty_gold=500)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/3/reminded", headers=_SERVICE_HEADERS)
        data = resp.json()
        assert data["title"] == "Check AC"
        assert data["zone"] == "lab"
        assert data["bounty_gold"] == 500


# ── GET /tasks/queue ───────────────────────────────────────────


class TestGetQueuedTasks:
    """GET /tasks/queue — list queued tasks."""

    def test_empty_queue(self):
        db = _make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/queue")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_queued_tasks(self):
        t1 = _make_task_obj(id=1, title="Queued A", is_queued=True, urgency=4)
        t2 = _make_task_obj(id=2, title="Queued B", is_queued=True, urgency=2)
        db = _make_mock_db([[t1, t2]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/queue")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["title"] == "Queued A"
        assert data[1]["title"] == "Queued B"

    def test_task_type_parsed_correctly(self):
        task = _make_task_obj(id=1, is_queued=True, task_type=["safety"])
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/queue")
        data = resp.json()
        assert data[0]["task_type"] == ["safety"]


# ── PUT /tasks/{id}/dispatch ───────────────────────────────────


class TestDispatchTask:
    """PUT /tasks/{task_id}/dispatch — mark queued task as dispatched."""

    def test_dispatch_success(self):
        task = _make_task_obj(id=1, is_queued=True)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/1/dispatch", headers=_SERVICE_HEADERS)
        assert resp.status_code == 200
        assert task.is_queued is False
        data = resp.json()
        assert data["is_queued"] is False

    def test_dispatch_not_found(self):
        db = _make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/999/dispatch", headers=_SERVICE_HEADERS)
        assert resp.status_code == 404

    def test_dispatch_sets_dispatched_at(self):
        """dispatched_at is set by func.now() on dispatch."""
        task = _make_task_obj(id=1, is_queued=True, dispatched_at=None)
        task.dispatched_at = None
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/1/dispatch", headers=_SERVICE_HEADERS)
        assert resp.status_code == 200
        # dispatched_at should have been set (func.now())
        assert task.dispatched_at is not None

    def test_dispatch_returns_full_task(self):
        task = _make_task_obj(id=3, title="Dispatch Me", is_queued=True, zone="lab")
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/3/dispatch", headers=_SERVICE_HEADERS)
        data = resp.json()
        assert data["title"] == "Dispatch Me"
        assert data["zone"] == "lab"


# ── GET /tasks/stats ───────────────────────────────────────────


class TestGetTaskStats:
    """GET /tasks/stats — system statistics."""

    def test_stats_all_zeros(self):
        sys_stats = _make_sys_stats(total_xp=0, tasks_completed=0, tasks_created=0)
        db = _make_mock_db([
            [0],           # queued count
            [0],           # completed last hour
            [0],           # active count
            [sys_stats],   # sys_stats
        ])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_xp"] == 0
        assert data["tasks_completed"] == 0
        assert data["tasks_created"] == 0
        assert data["tasks_active"] == 0
        assert data["tasks_queued"] == 0
        assert data["tasks_completed_last_hour"] == 0

    def test_stats_with_values(self):
        sys_stats = _make_sys_stats(total_xp=5000, tasks_completed=25, tasks_created=30)
        db = _make_mock_db([
            [3],           # queued count
            [2],           # completed last hour
            [5],           # active count
            [sys_stats],   # sys_stats
        ])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_xp"] == 5000
        assert data["tasks_completed"] == 25
        assert data["tasks_created"] == 30
        assert data["tasks_active"] == 5
        assert data["tasks_queued"] == 3
        assert data["tasks_completed_last_hour"] == 2

    def test_stats_null_counts_default_to_zero(self):
        """When count queries return None, values should default to 0."""
        sys_stats = _make_sys_stats()
        db = _make_mock_db([
            [None],        # queued count = None
            [None],        # completed last hour = None
            [None],        # active count = None
            [sys_stats],   # sys_stats
        ])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks_queued"] == 0
        assert data["tasks_completed_last_hour"] == 0
        assert data["tasks_active"] == 0

    def test_stats_creates_system_stats_if_missing(self):
        """When no SystemStats row exists, it should be created."""
        db = _make_mock_db([
            [0],     # queued count
            [0],     # completed last hour
            [0],     # active count
            [],      # sys_stats not found — will create new
        ])
        db.add = lambda obj: None

        async def _flush():
            pass
        db.flush = _flush

        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_xp"] == 0
        assert data["tasks_completed"] == 0
