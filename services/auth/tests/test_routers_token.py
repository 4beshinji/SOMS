"""Unit tests for services/auth/src/routers/token.py

Tests token refresh, revoke, and /me endpoints via FastAPI TestClient.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import (
    MockResult, make_mock_db, make_user_obj, make_oauth_obj,
    make_refresh_token_obj,
)
from database import get_db
from routers import token
from security import create_access_token, hash_refresh_token, create_refresh_token


def _create_test_app(db_mock=None):
    app = FastAPI()
    app.include_router(token.router)
    if db_mock is not None:
        app.dependency_overrides[get_db] = lambda: db_mock
    return app


# ── POST /token/refresh ─────────────────────────────────────────


class TestTokenRefresh:

    def test_valid_refresh_returns_new_tokens(self):
        raw, token_hash, family_id = create_refresh_token()
        stored_rt = make_refresh_token_obj(
            user_id=1, token_hash=token_hash, family_id=family_id,
        )
        user = make_user_obj(id=1, username="alice", display_name="Alice")

        # execute calls: 1) find refresh token → found
        #                2) find user → found
        db = make_mock_db([[stored_rt], [user]])
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.post("/token/refresh", json={"refresh_token": raw})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0
        assert data["user"]["id"] == 1
        assert data["user"]["username"] == "alice"

    def test_invalid_refresh_token_returns_401(self):
        # No matching token in DB
        db = make_mock_db([[]])
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.post("/token/refresh",
                           json={"refresh_token": "nonexistent"})
        assert resp.status_code == 401
        assert "Invalid refresh token" in resp.json()["detail"]

    def test_expired_refresh_token_returns_401(self):
        raw, token_hash, family_id = create_refresh_token()
        stored_rt = make_refresh_token_obj(
            user_id=1, token_hash=token_hash, family_id=family_id,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        db = make_mock_db([[stored_rt]])
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.post("/token/refresh", json={"refresh_token": raw})
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

    def test_revoked_token_not_found(self):
        """A revoked token is filtered out by the query (revoked_at == None)."""
        db = make_mock_db([[]])  # empty result = not found
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.post("/token/refresh",
                           json={"refresh_token": "revoked_one"})
        assert resp.status_code == 401

    def test_refresh_revokes_old_token(self):
        raw, token_hash, family_id = create_refresh_token()
        stored_rt = make_refresh_token_obj(
            user_id=1, token_hash=token_hash, family_id=family_id,
        )
        user = make_user_obj(id=1)

        db = make_mock_db([[stored_rt], [user]])
        app = _create_test_app(db)
        client = TestClient(app)

        client.post("/token/refresh", json={"refresh_token": raw})
        # The old token should have been revoked
        assert stored_rt.revoked_at is not None

    def test_refresh_issues_new_refresh_in_same_family(self):
        raw, token_hash, family_id = create_refresh_token()
        stored_rt = make_refresh_token_obj(
            user_id=1, token_hash=token_hash, family_id=family_id,
        )
        user = make_user_obj(id=1)

        db = make_mock_db([[stored_rt], [user]])
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.post("/token/refresh", json={"refresh_token": raw})
        assert resp.status_code == 200
        # A new refresh token was added to DB
        assert db.add.call_count == 1
        new_rt = db.add.call_args[0][0]
        assert new_rt.family_id == family_id
        assert new_rt.user_id == 1

    def test_refresh_with_deleted_user_returns_401(self):
        raw, token_hash, family_id = create_refresh_token()
        stored_rt = make_refresh_token_obj(
            user_id=999, token_hash=token_hash, family_id=family_id,
        )
        # User not found
        db = make_mock_db([[stored_rt], []])
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.post("/token/refresh", json={"refresh_token": raw})
        assert resp.status_code == 401
        assert "User not found" in resp.json()["detail"]


# ── POST /token/revoke ───────────────────────────────────────────


class TestTokenRevoke:

    def test_revoke_valid_token(self):
        raw, token_hash, family_id = create_refresh_token()
        stored_rt = make_refresh_token_obj(
            user_id=1, token_hash=token_hash, family_id=family_id,
            revoked_at=None,
        )
        # execute calls: 1) find by hash → found
        #                2) find family members → list
        sibling = make_refresh_token_obj(
            id=2, user_id=1, family_id=family_id, revoked_at=None,
        )
        db = make_mock_db([[stored_rt], [sibling]])
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.post("/token/revoke", json={"refresh_token": raw})
        assert resp.status_code == 200
        assert resp.json()["detail"] == "ok"
        assert stored_rt.revoked_at is not None

    def test_revoke_invalidates_entire_family(self):
        raw, token_hash, family_id = create_refresh_token()
        stored_rt = make_refresh_token_obj(
            user_id=1, token_hash=token_hash, family_id=family_id,
        )
        sibling = make_refresh_token_obj(
            id=2, user_id=1, family_id=family_id, revoked_at=None,
        )
        db = make_mock_db([[stored_rt], [sibling]])
        app = _create_test_app(db)
        client = TestClient(app)

        client.post("/token/revoke", json={"refresh_token": raw})
        # Both original and sibling should be revoked
        assert stored_rt.revoked_at is not None
        assert sibling.revoked_at is not None

    def test_revoke_nonexistent_token_returns_ok(self):
        """Revoking a token that doesn't exist should succeed silently."""
        db = make_mock_db([[]])
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.post("/token/revoke",
                           json={"refresh_token": "does_not_exist"})
        assert resp.status_code == 200
        assert resp.json()["detail"] == "ok"

    def test_revoke_already_revoked_is_idempotent(self):
        raw, token_hash, _ = create_refresh_token()
        stored_rt = make_refresh_token_obj(
            token_hash=token_hash,
            revoked_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db = make_mock_db([[stored_rt]])
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.post("/token/revoke", json={"refresh_token": raw})
        assert resp.status_code == 200


# ── GET /token/me ────────────────────────────────────────────────


class TestTokenMe:

    def test_valid_token_returns_user_info(self):
        access_token, _ = create_access_token(5, "eve", "Eve E")
        user = make_user_obj(id=5, username="eve", display_name="Eve E")
        oauth = make_oauth_obj(
            user_id=5, provider="github", provider_username="eve_gh",
            provider_avatar_url="https://avatar.example.com/eve",
        )

        db = make_mock_db([[user], [oauth]])
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.get("/token/me",
                          headers={"Authorization": f"Bearer {access_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 5
        assert data["username"] == "eve"
        assert data["display_name"] == "Eve E"
        assert data["provider"] == "github"
        assert data["provider_username"] == "eve_gh"

    def test_no_authorization_header_returns_422(self):
        """Missing required header → 422 Unprocessable Entity."""
        db = make_mock_db()
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.get("/token/me")
        assert resp.status_code == 422

    def test_invalid_bearer_prefix_returns_401(self):
        db = make_mock_db()
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.get("/token/me",
                          headers={"Authorization": "Basic abc123"})
        assert resp.status_code == 401
        assert "Invalid authorization header" in resp.json()["detail"]

    def test_expired_token_returns_401(self):
        import jwt
        from config import settings
        payload = {
            "sub": "1", "username": "x", "display_name": "X",
            "iss": "soms-auth",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
        }
        expired_tok = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

        db = make_mock_db()
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.get("/token/me",
                          headers={"Authorization": f"Bearer {expired_tok}"})
        assert resp.status_code == 401
        assert "Invalid or expired" in resp.json()["detail"]

    def test_deleted_user_returns_401(self):
        access_token, _ = create_access_token(999, "ghost", "Ghost")
        # User not found
        db = make_mock_db([[]])
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.get("/token/me",
                          headers={"Authorization": f"Bearer {access_token}"})
        assert resp.status_code == 401
        assert "User not found" in resp.json()["detail"]

    def test_user_without_oauth_shows_null_provider(self):
        access_token, _ = create_access_token(3, "local", "Local User")
        user = make_user_obj(id=3, username="local", display_name="Local User")
        # No oauth account found
        db = make_mock_db([[user], []])
        app = _create_test_app(db)
        client = TestClient(app)

        resp = client.get("/token/me",
                          headers={"Authorization": f"Bearer {access_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] is None
        assert data["provider_username"] is None
