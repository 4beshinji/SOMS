"""Unit tests for dashboard task router endpoints.

Tests GET /tasks/, POST /tasks/, PUT /tasks/{id}/reminded,
GET /tasks/queue, PUT /tasks/{id}/dispatch, GET /tasks/stats.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_db
from conftest import (
    MockResult, make_mock_db, make_task_obj, make_sys_stats, SERVICE_HEADERS,
)


# ── Helpers ─────────────────────────────────────────────────────


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
        db = make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_single_task(self):
        task = make_task_obj(id=1, title="Fix AC", json_encode_task_type=True)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert data[0]["title"] == "Fix AC"

    def test_returns_multiple_tasks(self):
        t1 = make_task_obj(id=1, title="Task A", json_encode_task_type=True)
        t2 = make_task_obj(id=2, title="Task B", json_encode_task_type=True)
        db = make_mock_db([[t1, t2]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_pagination_skip_limit(self):
        """Pagination params are accepted (actual filtering in DB)."""
        task = make_task_obj(id=5, json_encode_task_type=True)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/?skip=10&limit=5")
        assert resp.status_code == 200

    def test_task_type_parsed_from_json(self):
        """task_type stored as JSON string should be parsed to a list."""
        task = make_task_obj(id=1, task_type=["cleaning", "maintenance"],
                             json_encode_task_type=True)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        data = resp.json()
        assert data[0]["task_type"] == ["cleaning", "maintenance"]

    def test_null_task_type_becomes_empty_list(self):
        """task_type=None in DB should become [] in response."""
        task = make_task_obj(id=1, json_encode_task_type=True)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        data = resp.json()
        assert data[0]["task_type"] == []

    def test_invalid_json_task_type_becomes_empty_list(self):
        """Invalid JSON in task_type should gracefully become []."""
        task = make_task_obj(id=1, json_encode_task_type=True)
        task.task_type = "not-valid-json"
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/")
        data = resp.json()
        assert data[0]["task_type"] == []

    def test_task_fields_in_response(self):
        """Verify key fields are present in response."""
        task = make_task_obj(
            id=42, title="Water Plants", description="All zones",
            location="Lab", bounty_gold=500, urgency=3, zone="lab",
            region_id="tokyo", json_encode_task_type=True,
        )
        db = make_mock_db([[task]])
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
        sys_stats = make_sys_stats()
        # execute calls: Stage 1 query (no dup), Stage 2 skipped (no zone+task_type), sys_stats query, final result
        db = make_mock_db([
            [],            # Stage 1: no duplicate
            [sys_stats],   # _get_or_create_system_stats
        ])

        # After commit + refresh, the db.add'd object gets used
        db.add = lambda obj: None

        async def _refresh(obj):
            _new_task_refresh(obj, default_id=10)
        db.refresh = _refresh

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/tasks/", json={
            "title": "New Task",
            "description": "Do something",
            "location": "Room A",
            "bounty_gold": 1000,
            "zone": "main",
        }, headers=SERVICE_HEADERS)
        assert resp.status_code == 200
        assert sys_stats.tasks_created == 1

    def test_duplicate_stage1_exact_title_location(self):
        """Stage 1: exact title+location match → updates existing task."""
        existing = make_task_obj(id=5, title="Fix Light", location="Room A",
                                 json_encode_task_type=True)
        db = make_mock_db([
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
        }, headers=SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 5  # Same task ID
        assert existing.description == "Updated description"
        assert existing.bounty_gold == 2000

    def test_same_zone_task_type_overlap_creates_new(self):
        """Same zone + overlapping task_type but different category → new task.

        Stage 2 (zone+task_type overlap) was removed because it caused
        false merges (e.g., device-check title with humidity description).
        """
        sys_stats = make_sys_stats()
        db = make_mock_db([
            [],            # Stage 1: no exact match
            # Stage 1.5: titles have no category keywords → skipped
            [sys_stats],   # _get_or_create_system_stats
        ])

        db.add = lambda obj: None

        async def _refresh(obj):
            _new_task_refresh(obj, default_id=20)
        db.refresh = _refresh

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/tasks/", json={
            "title": "Different Title",
            "description": "New desc",
            "zone": "main",
            "task_type": ["cleaning"],
        }, headers=SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 20  # New task, not merged

    def test_stage1_5_duplicate_updates_title(self):
        """Stage 1.5 duplicate: title should be updated to the new value."""
        existing = make_task_obj(id=5, title="デバイス確認タスク",
                                 description="デバイスを調べる",
                                 zone="main", json_encode_task_type=True)
        db = make_mock_db([
            [],            # Stage 1: no exact match (different title)
            [existing],    # Stage 1.5: category candidates
        ])

        async def _refresh(obj):
            pass
        db.refresh = _refresh

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/tasks/", json={
            "title": "不明デバイスを調査してください",
            "description": "新しいデバイスが検出されました",
            "zone": "main",
        }, headers=SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 5  # Same task (Stage 1.5 match)
        assert existing.title == "不明デバイスを調査してください"  # Title updated

    def test_device_check_and_humidity_not_merged(self):
        """Regression: device-check title must NOT be merged with humidity task.

        This was the reported bug: title='デバイスネットワークの確認が必要'
        with description about low humidity.
        """
        existing = make_task_obj(id=7, title="デバイスネットワークの確認が必要",
                                 zone="main", task_type=["environment"],
                                 json_encode_task_type=True)
        sys_stats = make_sys_stats()
        db = make_mock_db([
            [],            # Stage 1: no exact match
            [existing],    # Stage 1.5: candidates (device_check vs humidity → no overlap)
            [sys_stats],   # _get_or_create_system_stats
        ])

        db.add = lambda obj: None

        async def _refresh(obj):
            _new_task_refresh(obj, default_id=20)
        db.refresh = _refresh

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/tasks/", json={
            "title": "加湿と換気を行ってください",
            "description": "湿度が29%と基準（30-60%）を下回っています。",
            "zone": "main",
            "task_type": ["environment"],
        }, headers=SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 20  # New task, NOT merged into device-check

    def test_duplicate_updates_voice_data_when_provided(self):
        """When updating a duplicate, voice data is only updated if provided."""
        existing = make_task_obj(id=5, title="Fix Light", location="Room A",
                                 json_encode_task_type=True)
        existing.announcement_audio_url = "/audio/old.mp3"
        existing.announcement_text = "Old text"
        db = make_mock_db([[existing]])

        async def _refresh(obj):
            pass
        db.refresh = _refresh

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/tasks/", json={
            "title": "Fix Light",
            "location": "Room A",
            "announcement_audio_url": "/audio/new.mp3",
        }, headers=SERVICE_HEADERS)
        assert resp.status_code == 200
        assert existing.announcement_audio_url == "/audio/new.mp3"
        # Text not provided, should keep old value
        assert existing.announcement_text == "Old text"

    def test_create_task_with_minimal_fields(self):
        """Create with just title (all others default)."""
        sys_stats = make_sys_stats()
        db = make_mock_db([
            [],            # Stage 1: no dup
            [sys_stats],   # sys_stats
        ])
        db.add = lambda obj: None

        async def _refresh(obj):
            _new_task_refresh(obj, default_id=1)
        db.refresh = _refresh

        app = _create_app(db)
        client = TestClient(app)
        resp = client.post("/tasks/", json={"title": "Simple Task"}, headers=SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Simple Task"
        assert data["bounty_gold"] == 10  # default
        assert data["urgency"] == 2       # default


# ── PUT /tasks/{id}/reminded ───────────────────────────────────


class TestMarkTaskReminded:
    """PUT /tasks/{task_id}/reminded — update last_reminded_at."""

    def test_success(self):
        task = make_task_obj(id=1, json_encode_task_type=True)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/1/reminded", headers=SERVICE_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        # last_reminded_at should be set (func.now() resolved by refresh mock)
        assert data["last_reminded_at"] is not None

    def test_not_found(self):
        db = make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/999/reminded", headers=SERVICE_HEADERS)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_reminded_returns_full_task(self):
        """Response should contain all task fields."""
        task = make_task_obj(id=3, title="Check AC", zone="lab", bounty_gold=500,
                             json_encode_task_type=True)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/3/reminded", headers=SERVICE_HEADERS)
        data = resp.json()
        assert data["title"] == "Check AC"
        assert data["zone"] == "lab"
        assert data["bounty_gold"] == 500


# ── GET /tasks/queue ───────────────────────────────────────────


class TestGetQueuedTasks:
    """GET /tasks/queue — list queued tasks."""

    def test_empty_queue(self):
        db = make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/queue")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_queued_tasks(self):
        t1 = make_task_obj(id=1, title="Queued A", is_queued=True, urgency=4,
                           json_encode_task_type=True)
        t2 = make_task_obj(id=2, title="Queued B", is_queued=True, urgency=2,
                           json_encode_task_type=True)
        db = make_mock_db([[t1, t2]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/queue")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["title"] == "Queued A"
        assert data[1]["title"] == "Queued B"

    def test_task_type_parsed_correctly(self):
        task = make_task_obj(id=1, is_queued=True, task_type=["safety"],
                             json_encode_task_type=True)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.get("/tasks/queue")
        data = resp.json()
        assert data[0]["task_type"] == ["safety"]


# ── PUT /tasks/{id}/dispatch ───────────────────────────────────


class TestDispatchTask:
    """PUT /tasks/{task_id}/dispatch — mark queued task as dispatched."""

    def test_dispatch_success(self):
        task = make_task_obj(id=1, is_queued=True, json_encode_task_type=True)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/1/dispatch", headers=SERVICE_HEADERS)
        assert resp.status_code == 200
        assert task.is_queued is False
        data = resp.json()
        assert data["is_queued"] is False

    def test_dispatch_not_found(self):
        db = make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/999/dispatch", headers=SERVICE_HEADERS)
        assert resp.status_code == 404

    def test_dispatch_sets_dispatched_at(self):
        """dispatched_at is set by func.now() on dispatch."""
        task = make_task_obj(id=1, is_queued=True, dispatched_at=None,
                             json_encode_task_type=True)
        task.dispatched_at = None
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/1/dispatch", headers=SERVICE_HEADERS)
        assert resp.status_code == 200
        # dispatched_at should have been set (func.now())
        assert task.dispatched_at is not None

    def test_dispatch_returns_full_task(self):
        task = make_task_obj(id=3, title="Dispatch Me", is_queued=True, zone="lab",
                             json_encode_task_type=True)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/3/dispatch", headers=SERVICE_HEADERS)
        data = resp.json()
        assert data["title"] == "Dispatch Me"
        assert data["zone"] == "lab"


# ── GET /tasks/stats ───────────────────────────────────────────


class TestGetTaskStats:
    """GET /tasks/stats — system statistics."""

    def test_stats_all_zeros(self):
        sys_stats = make_sys_stats(total_xp=0, tasks_completed=0, tasks_created=0)
        db = make_mock_db([
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
        sys_stats = make_sys_stats(total_xp=5000, tasks_completed=25, tasks_created=30)
        db = make_mock_db([
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
        sys_stats = make_sys_stats()
        db = make_mock_db([
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
        db = make_mock_db([
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
