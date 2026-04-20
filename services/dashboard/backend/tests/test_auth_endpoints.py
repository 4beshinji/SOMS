"""Unit tests for dashboard auth-protected endpoints.

Tests the auth guard behavior on PUT /tasks/{id}/accept and
PUT /tasks/{id}/complete. Uses mocked DB to isolate auth logic.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

# Ensure dashboard/backend and tests dir are importable
_TESTS_DIR = str(Path(__file__).resolve().parent)
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
for _d in (_TESTS_DIR, _BACKEND_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

os.environ.setdefault("JWT_SECRET", "test_jwt_secret_dashboard_32b!!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_db
from conftest import make_mock_db, make_token, auth_header, make_task_obj, make_sys_stats


# ── Helpers ─────────────────────────────────────────────────────


def _create_app(db_mock):
    from routers.tasks import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_mock
    return app


# ── Accept Task Auth Tests ─────────────────────────────────────


class TestAcceptTaskAuth:
    """Auth guard on PUT /tasks/{task_id}/accept."""

    def test_authenticated_matching_user_allowed(self):
        """JWT user_id == body.user_id → no 403."""
        task = make_task_obj(id=1)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=auth_header(sub=5))
        assert resp.status_code != 403

    def test_authenticated_different_user_returns_403(self):
        """JWT user_id != body.user_id → 403 Forbidden."""
        db = make_mock_db()
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=auth_header(sub=99))
        assert resp.status_code == 403
        assert "Cannot accept task for another user" in resp.json()["detail"]

    def test_missing_user_id_in_body_allowed(self):
        """body without user_id (defaults to None) → no 403."""
        task = make_task_obj(id=1)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={},
                          headers=auth_header(sub=99))
        assert resp.status_code != 403

    def test_task_not_found_returns_404(self):
        """Task doesn't exist → 404 (after auth passes)."""
        db = make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/999/accept",
                          json={"user_id": 5},
                          headers=auth_header(sub=5))
        assert resp.status_code == 404

    def test_completed_task_returns_400(self):
        """Already completed task → 400."""
        task = make_task_obj(id=1, is_completed=True)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=auth_header(sub=5))
        assert resp.status_code == 400
        assert "already completed" in resp.json()["detail"]

    def test_already_accepted_task_returns_400(self):
        """Already accepted task → 400."""
        task = make_task_obj(id=1, accepted_at=datetime.now(timezone.utc))
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=auth_header(sub=5))
        assert resp.status_code == 400
        assert "already accepted" in resp.json()["detail"]

    def test_403_before_404(self):
        """Auth check happens before task lookup — 403 even for nonexistent task."""
        db = make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/999/accept",
                          json={"user_id": 5},
                          headers=auth_header(sub=99))
        assert resp.status_code == 403

    def test_accept_sets_assigned_to(self):
        """Successful accept sets assigned_to and accepted_at."""
        task = make_task_obj(id=1)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=auth_header(sub=5))
        assert resp.status_code == 200
        assert task.assigned_to == 5


# ── Complete Task Auth Tests ────────────────────────────────────


class TestCompleteTaskAuth:
    """Auth guard on PUT /tasks/{task_id}/complete.

    Note: complete_task does NOT check auth_user vs body — it only
    receives auth_user via the dependency but doesn't compare user_id.
    """

    def test_authenticated_request_allowed(self):
        """Any authenticated user can complete — no user_id check."""
        task = make_task_obj(id=1, zone=None, assigned_to=None)
        sys_stats = make_sys_stats()
        db = make_mock_db([[task], [sys_stats]])

        with \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.put("/tasks/1/complete", json={},
                              headers=auth_header(sub=42))
            assert resp.status_code != 403

    def test_task_not_found_returns_404(self):
        db = make_mock_db([[]])
        app = _create_app(db)
        client = TestClient(app)
        resp = client.put("/tasks/999/complete", json={},
                          headers=auth_header(sub=1))
        assert resp.status_code == 404

    def test_complete_with_report(self):
        """Complete with report_status and completion_note."""
        task = make_task_obj(id=1, zone=None, assigned_to=None)
        sys_stats = make_sys_stats()
        db = make_mock_db([[task], [sys_stats]])

        with \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.put("/tasks/1/complete",
                              json={"report_status": "resolved", "completion_note": "Fixed"},
                              headers=auth_header(sub=1))
            assert resp.status_code != 403
            assert task.report_status == "resolved"
            assert task.completion_note == "Fixed"

    def test_completion_note_truncated_to_500(self):
        """completion_note is truncated to 500 chars."""
        task = make_task_obj(id=1, zone=None, assigned_to=None)
        sys_stats = make_sys_stats()
        db = make_mock_db([[task], [sys_stats]])

        with \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            client.put("/tasks/1/complete",
                       json={"completion_note": "X" * 1000},
                       headers=auth_header(sub=1))
            assert len(task.completion_note) == 500

    def test_complete_marks_is_completed(self):
        """Completing a task sets is_completed=True."""
        task = make_task_obj(id=1, zone=None, assigned_to=None)
        sys_stats = make_sys_stats()
        db = make_mock_db([[task], [sys_stats]])

        with \
             patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            resp = client.put("/tasks/1/complete", json={},
                              headers=auth_header(sub=1))
            assert resp.status_code == 200
            assert task.is_completed is True

    def test_complete_increments_system_stats(self):
        """Completing a task increments tasks_completed."""
        task = make_task_obj(id=1, zone=None, assigned_to=None)
        sys_stats = make_sys_stats()
        db = make_mock_db([[task], [sys_stats]])

        with patch("routers.tasks._publish_task_report"):
            app = _create_app(db)
            client = TestClient(app)
            client.put("/tasks/1/complete", json={},
                       headers=auth_header(sub=1))
            assert sys_stats.tasks_completed == 1


# ── Edge Cases ─────────────────────────────────────────────────


class TestAuthEdgeCases:

    def test_accept_auth_user_id_zero_system_wallet(self):
        """System wallet (user_id=0) authenticated, accepting for user_id=0."""
        task = make_task_obj(id=1)
        db = make_mock_db([[task]])
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 0},
                          headers=auth_header(sub=0))
        assert resp.status_code != 403

    def test_accept_auth_user_id_zero_mismatched(self):
        """System wallet (user_id=0) trying to accept for user_id=5 → 403."""
        db = make_mock_db()
        app = _create_app(db)
        client = TestClient(app)

        resp = client.put("/tasks/1/accept",
                          json={"user_id": 5},
                          headers=auth_header(sub=0))
        assert resp.status_code == 403

