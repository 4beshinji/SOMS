"""Shared fixtures and helpers for dashboard backend unit tests."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

# Ensure dashboard/backend is importable
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Ensure tests/ dir is importable (for `from conftest import ...` in test files)
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# Set test-safe environment before imports
os.environ.setdefault("JWT_SECRET", "test_jwt_secret_dashboard_32b!!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_service_token_for_unit_tests")

SERVICE_HEADERS = {"X-Service-Token": os.environ["INTERNAL_SERVICE_TOKEN"]}


# ── Mock DB Result Classes ────────────────────────────────────


class MockScalars:
    """Mock for SQLAlchemy Result.scalars()."""

    def __init__(self, items=None):
        self._items = list(items) if items else []

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return self._items


class MockResult:
    """Unified mock for SQLAlchemy Result objects.

    Supports all access patterns used across test files:
    - .scalars().first() / .scalars().all()
    - .scalar()
    - .scalar_one_or_none()
    - .all()

    Parameters:
        items: List of result items.
        scalar_value: Explicit value for scalar_one_or_none() (takes priority
                      over items when not None).  Also used by scalar() when
                      provided via the ``scalar_val`` alias.
    """

    def __init__(self, items=None, scalar_value=None, scalar_val=None):
        self._items = list(items) if items else []
        # Accept both kwarg names for convenience
        self._scalar_override = scalar_value if scalar_value is not None else scalar_val

    def scalars(self):
        return MockScalars(self._items)

    def scalar(self):
        if self._scalar_override is not None:
            return self._scalar_override
        return self._items[0] if self._items else None

    def scalar_one_or_none(self):
        if self._scalar_override is not None:
            return self._scalar_override
        return self._items[0] if self._items else None

    def all(self):
        return self._items


def make_mock_db(execute_side_effects=None, *, track_added=False,
                 refresh_defaults=None):
    """Create a unified AsyncMock database session.

    Parameters:
        execute_side_effects: List of MockResult objects or plain lists.
            Plain lists are automatically wrapped in MockResult.
            When None, db.execute returns an empty MockResult.
        track_added: When True, db.add captures objects into db._added list
            (used by shopping/inventory tests).
        refresh_defaults: Optional dict of {attr: default_value} to apply
            during db.refresh for newly-created objects.

    Returns:
        AsyncMock db session.  When track_added=True, db._added is available.
    """
    db = AsyncMock()

    if execute_side_effects is not None:
        results = []
        for item in execute_side_effects:
            if isinstance(item, MockResult):
                results.append(item)
            else:
                results.append(MockResult(item))
        db.execute.side_effect = results
    else:
        db.execute.return_value = MockResult([])

    if track_added:
        _added = []

        def _sync_add(obj):
            _added.append(obj)

        db.add = _sync_add
        db._added = _added

    async def _refresh(obj):
        # Common: assign id and created_at for newly-created objects
        if not hasattr(obj, 'id') or obj.id is None:
            obj.id = 1
        if hasattr(obj, 'created_at') and obj.created_at is None:
            obj.created_at = datetime.now(timezone.utc)

        # Replace func.now() sentinel values with real datetimes
        for attr in ('accepted_at', 'completed_at', 'dispatched_at',
                     'last_reminded_at'):
            val = getattr(obj, attr, None)
            if val is not None and not isinstance(val, datetime):
                setattr(obj, attr, datetime.now(timezone.utc))

        # Apply service-specific column defaults
        if refresh_defaults:
            for attr, default in refresh_defaults.items():
                if getattr(obj, attr, None) is None:
                    setattr(obj, attr, default)

    db.refresh = _refresh
    return db


# ── JWT Token Helpers ─────────────────────────────────────────


def make_token(sub=1, username="testuser", display_name="Test User",
               iss="soms-auth", exp_delta_sec=900, secret=None,
               extra_claims=None):
    """Build a JWT token for testing.

    Parameters:
        sub: User ID (will be str-encoded in the JWT payload).
        username: Username claim.
        display_name: Display name claim.
        iss: Issuer claim.
        exp_delta_sec: Seconds until expiry (negative = already expired).
        secret: Signing secret (defaults to JWT_SECRET from env).
        extra_claims: Optional dict of additional claims to merge into payload.
    """
    import jwt as pyjwt
    from jwt_auth import JWT_SECRET

    payload = {
        "sub": str(sub),
        "username": username,
        "display_name": display_name,
        "iss": iss,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=exp_delta_sec),
        "iat": datetime.now(timezone.utc),
    }
    if extra_claims:
        payload.update(extra_claims)
    return pyjwt.encode(payload, secret or JWT_SECRET, algorithm="HS256")


def auth_header(sub=1, **kwargs):
    """Build an Authorization header dict with a valid JWT."""
    return {"Authorization": f"Bearer {make_token(sub=sub, **kwargs)}"}


# ── Fake Task Object ─────────────────────────────────────────


def make_task_obj(
    id=1,
    title="Test Task",
    description="A task description",
    location="Office",
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
    json_encode_task_type=False,
):
    """Create a fake Task object for testing.

    Parameters:
        json_encode_task_type: When True, task_type lists are JSON-encoded
            (matching how task_endpoints.py stores them).  When False,
            task_type is stored as-is.
    """
    import json
    now = datetime.now(timezone.utc)

    class FakeTask:
        """Minimal Task stand-in that behaves like SQLAlchemy model."""
        pass

    task = FakeTask()
    task.id = id
    task.title = title
    task.description = description
    task.location = location
    task.is_completed = is_completed
    task.is_queued = is_queued
    task.created_at = now
    task.completed_at = None
    task.dispatched_at = dispatched_at if dispatched_at is not None else now
    task.expires_at = expires_at
    if json_encode_task_type:
        task.task_type = json.dumps(task_type) if task_type else None
    else:
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
    task.last_reminded_at = last_reminded_at
    task.report_status = report_status
    task.completion_note = completion_note
    task.region_id = region_id
    return task


def make_sys_stats(tasks_completed=0, tasks_created=0):
    """Create a fake SystemStats object for testing."""

    class FakeStats:
        pass

    s = FakeStats()
    s.id = 1
    s.tasks_completed = tasks_completed
    s.tasks_created = tasks_created
    return s
