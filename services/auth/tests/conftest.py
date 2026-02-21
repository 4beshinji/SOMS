"""Shared fixtures and helpers for auth service unit tests."""
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_THIS_DIR = str(Path(__file__).resolve().parent)
AUTH_SRC = str(Path(__file__).resolve().parent.parent / "src")
WALLET_SRC = str(Path(__file__).resolve().parent.parent.parent / "wallet" / "src")

# Add directories to sys.path so all test-file imports work:
#   - tests/ dir itself  → `from conftest import ...`
#   - auth/src/          → `from security import ...`  (must be BEFORE wallet/src)
#   - wallet/src/        → `from jwt_auth import ...`
# Insert order matters: last insert(0) ends up first.
# We want: auth/src before wallet/src (both have database.py).
if WALLET_SRC not in sys.path:
    sys.path.insert(0, WALLET_SRC)
if AUTH_SRC not in sys.path:
    sys.path.insert(0, AUTH_SRC)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# Set test-safe environment BEFORE importing any auth modules
os.environ.setdefault("JWT_SECRET", "test_secret_key_for_unit_tests")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("SLACK_CLIENT_ID", "slack_test_id")
os.environ.setdefault("SLACK_CLIENT_SECRET", "slack_test_secret")
os.environ.setdefault("GITHUB_CLIENT_ID", "github_test_id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "github_test_secret")
os.environ.setdefault("AUTH_BASE_URL", "https://test.example.com/api/auth")
os.environ.setdefault("FRONTEND_URL", "https://test.example.com")


# ── Mock DB helpers ──────────────────────────────────────────────


class MockScalars:
    """Mimics SQLAlchemy Result.scalars()."""

    def __init__(self, items=None):
        self._items = list(items) if items else []

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return self._items


class MockResult:
    """Mimics SQLAlchemy Result returned by session.execute()."""

    def __init__(self, items=None):
        self._items = list(items) if items else []

    def scalars(self):
        return MockScalars(self._items)


def make_mock_db(execute_side_effects=None):
    """Create a mock AsyncSession.

    Args:
        execute_side_effects: list of lists — each inner list is the items
            for one successive call to db.execute().scalars().first()/all().
    """
    db = AsyncMock()
    if execute_side_effects is not None:
        db.execute.side_effect = [MockResult(items) for items in execute_side_effects]
    else:
        db.execute.return_value = MockResult([])
    return db


def make_user_obj(id=1, username="testuser", display_name="Test User",
                  global_user_id=None, is_active=True):
    """Create a mock User row object."""
    user = MagicMock()
    user.id = id
    user.username = username
    user.display_name = display_name
    user.global_user_id = global_user_id
    user.is_active = is_active
    return user


def make_oauth_obj(id=1, user_id=1, provider="github",
                   provider_user_id="12345", provider_username="octocat",
                   provider_email="octo@example.com",
                   provider_avatar_url="https://example.com/avatar.png",
                   provider_data=None):
    """Create a mock OAuthAccount row object."""
    oauth = MagicMock()
    oauth.id = id
    oauth.user_id = user_id
    oauth.provider = provider
    oauth.provider_user_id = provider_user_id
    oauth.provider_username = provider_username
    oauth.provider_email = provider_email
    oauth.provider_avatar_url = provider_avatar_url
    oauth.provider_data = provider_data or {}
    oauth.created_at = None
    return oauth


def make_refresh_token_obj(id=1, user_id=1, token_hash="abc",
                           family_id=None, expires_at=None, revoked_at=None):
    """Create a mock RefreshToken row object."""
    from datetime import datetime, timedelta, timezone
    import uuid

    rt = MagicMock()
    rt.id = id
    rt.user_id = user_id
    rt.token_hash = token_hash
    rt.family_id = family_id or uuid.uuid4()
    rt.expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(days=30))
    rt.revoked_at = revoked_at
    return rt
