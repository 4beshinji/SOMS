"""Unit tests for JWT authentication middleware.

Tests the jwt_auth.py module used by wallet and dashboard backends.
Both services share the same code, so we test one copy.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

# wallet/src is on sys.path via conftest.py
from jwt_auth import AuthUser, get_current_user, require_auth, JWT_SECRET


# ── Helper ───────────────────────────────────────────────────────


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


def _create_test_app():
    """Create a FastAPI app with two test endpoints using the middleware."""
    app = FastAPI()

    @app.get("/optional")
    async def optional_endpoint(user=Depends(get_current_user)):
        if user is None:
            return {"user": None}
        return {"user": {"id": user.id, "username": user.username}}

    @app.get("/required")
    async def required_endpoint(user=Depends(require_auth)):
        return {"user": {"id": user.id, "username": user.username}}

    return app


# ── get_current_user ─────────────────────────────────────────────


class TestGetCurrentUser:

    def test_no_header_returns_none(self):
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/optional")
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_empty_header_returns_none(self):
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/optional", headers={"Authorization": ""})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_non_bearer_prefix_returns_none(self):
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/optional", headers={"Authorization": "Basic abc"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_valid_token_returns_user(self):
        token = _make_token(sub=42, username="alice")
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/optional",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()["user"]
        assert data["id"] == 42
        assert data["username"] == "alice"

    def test_expired_token_returns_none(self):
        token = _make_token(exp_delta_sec=-60)
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/optional",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_wrong_secret_returns_none(self):
        token = _make_token(secret="wrong_secret_key")
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/optional",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_wrong_issuer_returns_none(self):
        token = _make_token(iss="not-soms")
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/optional",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_malformed_token_returns_none(self):
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/optional",
                          headers={"Authorization": "Bearer not.a.valid.jwt"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_missing_sub_claim_returns_none(self):
        """Token without 'sub' → KeyError caught → None."""
        payload = {
            "username": "nosub", "display_name": "No Sub",
            "iss": "soms-auth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/optional",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None


# ── require_auth ─────────────────────────────────────────────────


class TestRequireAuth:

    def test_no_token_returns_401(self):
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/required")
        assert resp.status_code == 401
        assert "Authentication required" in resp.json()["detail"]

    def test_invalid_token_returns_401(self):
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/required",
                          headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401

    def test_valid_token_returns_user(self):
        token = _make_token(sub=7, username="bob")
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/required",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"]["id"] == 7

    def test_expired_token_returns_401(self):
        token = _make_token(exp_delta_sec=-60)
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/required",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


# ── AuthUser dataclass ───────────────────────────────────────────


class TestAuthUserDataclass:

    def test_fields(self):
        user = AuthUser(id=1, username="u", display_name="U")
        assert user.id == 1
        assert user.username == "u"
        assert user.display_name == "U"

    def test_equality(self):
        a = AuthUser(id=1, username="a", display_name="A")
        b = AuthUser(id=1, username="a", display_name="A")
        assert a == b

    def test_inequality(self):
        a = AuthUser(id=1, username="a", display_name="A")
        b = AuthUser(id=2, username="b", display_name="B")
        assert a != b
