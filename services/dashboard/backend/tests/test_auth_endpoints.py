"""Unit tests for dashboard auth-protected endpoints.

Tests the auth guard behavior on PUT /tasks/{id}/accept and
PUT /tasks/{id}/complete. Uses mocked DB to isolate auth logic.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

# Ensure dashboard/backend is importable
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ.setdefault("JWT_SECRET", "test_jwt_secret_dashboard_32b!!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jwt_auth import JWT_SECRET
from database import get_db


# ── Helpers ─────────────────────────────────────────────────────


def _make_token(sub=1, username="testuser", display_name="Test User",
                iss="soms-auth", exp_delta_sec=900, secret=None):
    payload = {
        "sub": str(sub),
        "username": username,
        "display_name": display_name,
        "iss": iss,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=exp_delta_sec),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, secret or JWT_SECRET, algorithm="HS256")


def _auth_header(sub=1, **kwargs):
    return {"Authorization": f"Bearer {_make_token(sub=sub, **kwargs)}"}


def _make_task_obj(
    id=1,
    title="Test Task",
    description="Description",
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
    report_status=None,
    completion_note=None,
    region_id="local",
):
    """Create a plain object (not MagicMock) for Task to avoid Pydantic issues."""
    now = datetime.now(timezone.utc)

    class FakeTask:
        """Minimal Task stand-in that behaves like SQLAlchemy model for _task_to_response."""
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
    task.dispatched_at = now
    task.expires_at = None
    task.task_type = task_type
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
    task.last_reminded_at = None
    task.report_status = report_status
    task.completion_note = completion_note
    task.region_id = region_id
    return task


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
    # Make commit and refresh properly async and set accepted_at to real datetime
    original_refresh = db.refresh

    async def _refresh(obj):
        # When the router sets accepted_at = func.now(), replace with real datetime
        if hasattr(obj, 'accepted_at') and obj.accepted_at is not None and not isinstance(obj.accepted_at, datetime):
            obj.accepted_at = datetime.now(timezone.utc)
        # Same for completed_at
        if hasattr(obj, 'completed_at') and obj.completed_at is not None and not isinstance(obj.completed_at, datetime):
            obj.completed_at = datetime.now(timezone.utc)

    db.refresh = _refresh
    return db


def _create_app(db_mock):
    from routers.tasks import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_mock
    return app


# ── Accept Task Auth Tests ─────────────────────────────────────


class TestAcceptTaskAuth:
    """Auth guard on PUT /tasks/{task_id}/accept."""

    def test_unauthenticated_request_allowed(self):
        """No JWT → auth_user=None → no 403, proceeds to task lookup."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept", json={"user_id": 5})
        assert resp.status_code != 403

    def test_authenticated_matching_user_allowed(self):
        """JWT user_id == body.user_id → no 403."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=_auth_header(sub=5))
        assert resp.status_code != 403

    def test_authenticated_different_user_returns_403(self):
        """JWT user_id != body.user_id → 403 Forbidden."""
        db = _make_mock_db()
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=_auth_header(sub=99))
        assert resp.status_code == 403
        assert "Cannot accept task for another user" in resp.json()["detail"]

    def test_null_user_id_in_body_always_allowed(self):
        """body.user_id=None (anonymous kiosk accept) → no 403 even if authenticated."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": None},
                          headers=_auth_header(sub=99))
        assert resp.status_code != 403

    def test_missing_user_id_in_body_allowed(self):
        """body without user_id (defaults to None) → no 403."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={},
                          headers=_auth_header(sub=99))
        assert resp.status_code != 403

    def test_expired_token_treated_as_unauthenticated(self):
        """Expired JWT → auth_user=None → no 403."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers={"Authorization": f"Bearer {_make_token(sub=99, exp_delta_sec=-60)}"})
        assert resp.status_code != 403

    def test_wrong_secret_treated_as_unauthenticated(self):
        """Token with wrong secret → auth_user=None → no 403."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers={"Authorization": f"Bearer {_make_token(sub=99, secret='wrong_secret_32bytes_longgggg!!')}"})
        assert resp.status_code != 403

    def test_task_not_found_returns_404(self):
        """Task doesn't exist → 404 (after auth passes)."""
        db = _make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/999/accept",
                          json={"user_id": 5},
                          headers=_auth_header(sub=5))
        assert resp.status_code == 404

    def test_completed_task_returns_400(self):
        """Already completed task → 400."""
        task = _make_task_obj(id=1, is_completed=True)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=_auth_header(sub=5))
        assert resp.status_code == 400
        assert "already completed" in resp.json()["detail"]

    def test_already_accepted_task_returns_400(self):
        """Already accepted task → 400."""
        task = _make_task_obj(id=1, accepted_at=datetime.now(timezone.utc))
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=_auth_header(sub=5))
        assert resp.status_code == 400
        assert "already accepted" in resp.json()["detail"]

    def test_403_before_404(self):
        """Auth check happens before task lookup — 403 even for nonexistent task."""
        db = _make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/999/accept",
                          json={"user_id": 5},
                          headers=_auth_header(sub=99))
        assert resp.status_code == 403

    def test_403_detail_message(self):
        db = _make_mock_db()
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 10},
                          headers=_auth_header(sub=20))
        assert resp.json()["detail"] == "Cannot accept task for another user"

    def test_accept_sets_assigned_to(self):
        """Successful accept sets assigned_to and accepted_at."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=_auth_header(sub=5))
        assert resp.status_code == 200
        assert task.assigned_to == 5


# ── Complete Task Auth Tests ────────────────────────────────────


def _make_sys_stats():
    class FakeStats:
        pass
    s = FakeStats()
    s.id = 1
    s.total_xp = 0
    s.tasks_completed = 0
    s.tasks_created = 0
    return s


class TestCompleteTaskAuth:
    """Auth guard on PUT /tasks/{task_id}/complete.

    Note: complete_task does NOT check auth_user vs body — it only
    receives auth_user via the dependency but doesn't compare user_id.
    """

    def test_unauthenticated_request_allowed(self):
        """No JWT → auth_user=None → proceeds normally."""
        task = _make_task_obj(id=1, zone=None, assigned_to=None, bounty_xp=0)
        sys_stats = _make_sys_stats()
        db = _make_mock_db([[task], [sys_stats]])

        with patch("routers.tasks._grant_device_xp"), \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.put("/tasks/1/complete", json={})
            assert resp.status_code != 403

    def test_authenticated_request_allowed(self):
        """Any authenticated user can complete — no user_id check."""
        task = _make_task_obj(id=1, zone=None, assigned_to=None, bounty_xp=0)
        sys_stats = _make_sys_stats()
        db = _make_mock_db([[task], [sys_stats]])

        with patch("routers.tasks._grant_device_xp"), \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.put("/tasks/1/complete", json={},
                              headers=_auth_header(sub=42))
            assert resp.status_code != 403

    def test_expired_token_treated_as_unauthenticated(self):
        """Expired JWT → auth_user=None → still works."""
        task = _make_task_obj(id=1, zone=None, assigned_to=None, bounty_xp=0)
        sys_stats = _make_sys_stats()
        db = _make_mock_db([[task], [sys_stats]])

        with patch("routers.tasks._grant_device_xp"), \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.put("/tasks/1/complete", json={},
                              headers={"Authorization": f"Bearer {_make_token(sub=1, exp_delta_sec=-60)}"})
            assert resp.status_code != 403

    def test_task_not_found_returns_404(self):
        db = _make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/999/complete", json={},
                          headers=_auth_header(sub=1))
        assert resp.status_code == 404

    def test_complete_with_report(self):
        """Complete with report_status and completion_note."""
        task = _make_task_obj(id=1, zone=None, assigned_to=None, bounty_xp=0)
        sys_stats = _make_sys_stats()
        db = _make_mock_db([[task], [sys_stats]])

        with patch("routers.tasks._grant_device_xp"), \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.put("/tasks/1/complete",
                              json={"report_status": "resolved", "completion_note": "Fixed"},
                              headers=_auth_header(sub=1))
            assert resp.status_code != 403
            assert task.report_status == "resolved"
            assert task.completion_note == "Fixed"

    def test_completion_note_truncated_to_500(self):
        """completion_note is truncated to 500 chars."""
        task = _make_task_obj(id=1, zone=None, assigned_to=None, bounty_xp=0)
        sys_stats = _make_sys_stats()
        db = _make_mock_db([[task], [sys_stats]])

        with patch("routers.tasks._grant_device_xp"), \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            client.put("/tasks/1/complete",
                       json={"completion_note": "X" * 1000})
            assert len(task.completion_note) == 500

    def test_complete_marks_is_completed(self):
        """Completing a task sets is_completed=True."""
        task = _make_task_obj(id=1, zone=None, assigned_to=None, bounty_xp=0)
        sys_stats = _make_sys_stats()
        db = _make_mock_db([[task], [sys_stats]])

        with patch("routers.tasks._grant_device_xp"), \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.put("/tasks/1/complete", json={})
            assert resp.status_code == 200
            assert task.is_completed is True

    def test_complete_increments_system_stats(self):
        """Completing a task increments tasks_completed and adds bounty_xp."""
        task = _make_task_obj(id=1, zone=None, assigned_to=None, bounty_xp=100)
        sys_stats = _make_sys_stats()
        db = _make_mock_db([[task], [sys_stats]])

        with patch("routers.tasks._grant_device_xp"), \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            client.put("/tasks/1/complete", json={})
            assert sys_stats.tasks_completed == 1
            assert sys_stats.total_xp == 100


# ── Edge Cases ─────────────────────────────────────────────────


class TestAuthEdgeCases:

    def test_accept_with_wrong_issuer_treated_as_unauthenticated(self):
        """Token with wrong issuer → auth_user=None → no 403."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers={"Authorization": f"Bearer {_make_token(sub=99, iss='evil')}"})
        assert resp.status_code != 403

    def test_accept_with_non_bearer_prefix_treated_as_unauthenticated(self):
        """'Basic' prefix → auth_user=None → no 403."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers={"Authorization": "Basic sometoken"})
        assert resp.status_code != 403

    def test_accept_auth_user_id_zero_system_wallet(self):
        """System wallet (user_id=0) authenticated, accepting for user_id=0."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 0},
                          headers=_auth_header(sub=0))
        assert resp.status_code != 403

    def test_accept_auth_user_id_zero_mismatched(self):
        """System wallet (user_id=0) trying to accept for user_id=5 → 403."""
        db = _make_mock_db()
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=_auth_header(sub=0))
        assert resp.status_code == 403

    def test_malformed_jwt_in_accept_treated_as_unauthenticated(self):
        """Malformed JWT → no 403."""
        task = _make_task_obj(id=1)
        db = _make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers={"Authorization": "Bearer not.valid.jwt"})
        assert resp.status_code != 403

    def test_malformed_jwt_in_complete_treated_as_unauthenticated(self):
        """Malformed JWT on complete → no 403."""
        task = _make_task_obj(id=1, zone=None, assigned_to=None, bounty_xp=0)
        sys_stats = _make_sys_stats()
        db = _make_mock_db([[task], [sys_stats]])

        with patch("routers.tasks._grant_device_xp"), \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.put("/tasks/1/complete", json={},
                              headers={"Authorization": "Bearer not.valid.jwt"})
            assert resp.status_code != 403
