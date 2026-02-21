"""Unit tests for dashboard backend JWT authentication middleware.

Tests get_current_user (optional), require_auth (required),
AuthUser dataclass, and JWT validation edge cases.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure dashboard/backend is importable
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Set JWT_SECRET before importing jwt_auth (module-level os.getenv)
os.environ.setdefault("JWT_SECRET", "test_jwt_secret_dashboard_32b!!")

import jwt
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from jwt_auth import AuthUser, get_current_user, require_auth, JWT_SECRET, JWT_ALGORITHM


# ── Helpers ─────────────────────────────────────────────────────


def _make_token(
    sub=1,
    username="testuser",
    display_name="Test User",
    iss="soms-auth",
    exp_delta_sec=900,
    secret=None,
    extra_claims=None,
):
    """Build a JWT token for testing."""
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
    return jwt.encode(payload, secret or JWT_SECRET, algorithm="HS256")


def _create_app():
    """Minimal FastAPI app with both optional and required auth endpoints."""
    app = FastAPI()

    @app.get("/optional")
    async def optional_endpoint(user=Depends(get_current_user)):
        if user is None:
            return {"user": None}
        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
            }
        }

    @app.get("/required")
    async def required_endpoint(user=Depends(require_auth)):
        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
            }
        }

    return app


# ── AuthUser dataclass ──────────────────────────────────────────


class TestAuthUser:

    def test_fields(self):
        user = AuthUser(id=42, username="alice", display_name="Alice A")
        assert user.id == 42
        assert user.username == "alice"
        assert user.display_name == "Alice A"

    def test_id_is_int(self):
        user = AuthUser(id=7, username="u", display_name="U")
        assert isinstance(user.id, int)

    def test_equality(self):
        a = AuthUser(id=1, username="a", display_name="A")
        b = AuthUser(id=1, username="a", display_name="A")
        assert a == b

    def test_inequality_different_id(self):
        a = AuthUser(id=1, username="a", display_name="A")
        b = AuthUser(id=2, username="a", display_name="A")
        assert a != b

    def test_inequality_different_username(self):
        a = AuthUser(id=1, username="a", display_name="A")
        b = AuthUser(id=1, username="b", display_name="A")
        assert a != b

    def test_inequality_different_display_name(self):
        a = AuthUser(id=1, username="a", display_name="A")
        b = AuthUser(id=1, username="a", display_name="B")
        assert a != b

    def test_repr_contains_fields(self):
        user = AuthUser(id=1, username="u", display_name="U")
        r = repr(user)
        assert "1" in r
        assert "u" in r


# ── get_current_user (optional auth) ────────────────────────────


class TestGetCurrentUser:

    def test_no_header_returns_none(self):
        client = TestClient(_create_app())
        resp = client.get("/optional")
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_empty_header_returns_none(self):
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": ""})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_non_bearer_prefix_returns_none(self):
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": "Basic abc"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_bearer_lowercase_returns_none(self):
        """'bearer' (lowercase) should not match 'Bearer '."""
        token = _make_token()
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_bearer_no_space_returns_none(self):
        """'BearerTOKEN' (no space) should not be parsed."""
        token = _make_token()
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer{token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_valid_token_returns_user(self):
        token = _make_token(sub=42, username="alice", display_name="Alice A")
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()["user"]
        assert data["id"] == 42
        assert data["username"] == "alice"
        assert data["display_name"] == "Alice A"

    def test_sub_converted_to_int(self):
        """sub claim is a string in JWT but should become int in AuthUser."""
        token = _make_token(sub=999)
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()["user"]
        assert data["id"] == 999
        assert isinstance(data["id"], int)

    def test_expired_token_returns_none(self):
        token = _make_token(exp_delta_sec=-60)
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_just_expired_token_returns_none(self):
        """Token that expired 1 second ago."""
        token = _make_token(exp_delta_sec=-1)
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_wrong_secret_returns_none(self):
        token = _make_token(secret="wrong_secret_key_that_is_long!!")
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_wrong_issuer_returns_none(self):
        token = _make_token(iss="not-soms")
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_missing_issuer_returns_none(self):
        """Token without iss claim should fail issuer validation."""
        payload = {
            "sub": "1",
            "username": "x",
            "display_name": "X",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_malformed_token_returns_none(self):
        client = TestClient(_create_app())
        resp = client.get("/optional",
                          headers={"Authorization": "Bearer not.a.valid.jwt"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_empty_bearer_token_returns_none(self):
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": "Bearer "})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_tampered_signature_returns_none(self):
        token = _make_token()
        parts = token.split(".")
        sig = parts[2]
        tampered = "A" if sig[0] != "A" else "B"
        parts[2] = tampered + sig[1:]
        client = TestClient(_create_app())
        resp = client.get("/optional",
                          headers={"Authorization": f"Bearer {'.'.join(parts)}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_tampered_payload_returns_none(self):
        token = _make_token()
        parts = token.split(".")
        payload_part = parts[1]
        tampered = "A" if payload_part[0] != "A" else "B"
        parts[1] = tampered + payload_part[1:]
        client = TestClient(_create_app())
        resp = client.get("/optional",
                          headers={"Authorization": f"Bearer {'.'.join(parts)}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_missing_sub_claim_returns_none(self):
        """Token without sub → KeyError caught → None."""
        payload = {
            "username": "nosub",
            "display_name": "No Sub",
            "iss": "soms-auth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_non_numeric_sub_returns_none(self):
        """sub that can't be int() → ValueError caught → None."""
        payload = {
            "sub": "not_a_number",
            "username": "x",
            "display_name": "X",
            "iss": "soms-auth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_missing_username_defaults_to_empty(self):
        """Missing username claim → payload.get defaults to ''."""
        payload = {
            "sub": "1",
            "display_name": "Just Display",
            "iss": "soms-auth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()["user"]
        assert data["id"] == 1
        assert data["username"] == ""

    def test_missing_display_name_defaults_to_empty(self):
        """Missing display_name claim → payload.get defaults to ''."""
        payload = {
            "sub": "1",
            "username": "u",
            "iss": "soms-auth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()["user"]
        assert data["display_name"] == ""

    def test_large_user_id(self):
        token = _make_token(sub=2147483647)  # max 32-bit int
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["user"]["id"] == 2147483647

    def test_zero_user_id(self):
        """System wallet uses user_id=0."""
        token = _make_token(sub=0)
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["user"]["id"] == 0

    def test_unicode_display_name(self):
        token = _make_token(display_name="田中太郎")
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["user"]["display_name"] == "田中太郎"

    def test_hs384_algorithm_rejected(self):
        """Token signed with HS384 should be rejected (only HS256 allowed)."""
        payload = {
            "sub": "1", "username": "x", "display_name": "X",
            "iss": "soms-auth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS384")
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_none_algorithm_rejected(self):
        """Token with alg=none should be rejected."""
        import base64, json
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        payload_data = {
            "sub": "1", "username": "x", "display_name": "X",
            "iss": "soms-auth",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
        }
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b"=").decode()
        token = f"{header}.{payload_b64}."
        client = TestClient(_create_app())
        resp = client.get("/optional", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["user"] is None


# ── require_auth (mandatory auth) ──────────────────────────────


class TestRequireAuth:

    def test_no_token_returns_401(self):
        client = TestClient(_create_app())
        resp = client.get("/required")
        assert resp.status_code == 401
        assert "Authentication required" in resp.json()["detail"]

    def test_empty_header_returns_401(self):
        client = TestClient(_create_app())
        resp = client.get("/required", headers={"Authorization": ""})
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        client = TestClient(_create_app())
        resp = client.get("/required",
                          headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401

    def test_expired_token_returns_401(self):
        token = _make_token(exp_delta_sec=-60)
        client = TestClient(_create_app())
        resp = client.get("/required",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self):
        token = _make_token(secret="wrong_secret_key_that_is_long!!")
        client = TestClient(_create_app())
        resp = client.get("/required",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_wrong_issuer_returns_401(self):
        token = _make_token(iss="evil-service")
        client = TestClient(_create_app())
        resp = client.get("/required",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_valid_token_returns_user(self):
        token = _make_token(sub=7, username="bob", display_name="Bob B")
        client = TestClient(_create_app())
        resp = client.get("/required",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()["user"]
        assert data["id"] == 7
        assert data["username"] == "bob"
        assert data["display_name"] == "Bob B"

    def test_non_numeric_sub_returns_401(self):
        payload = {
            "sub": "abc",
            "username": "x", "display_name": "X",
            "iss": "soms-auth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        client = TestClient(_create_app())
        resp = client.get("/required", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_missing_sub_returns_401(self):
        payload = {
            "username": "x", "display_name": "X",
            "iss": "soms-auth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        client = TestClient(_create_app())
        resp = client.get("/required", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


# ── Module-level constants ──────────────────────────────────────


class TestModuleConstants:

    def test_jwt_algorithm_is_hs256(self):
        assert JWT_ALGORITHM == "HS256"

    def test_jwt_secret_from_env(self):
        assert JWT_SECRET == os.environ.get("JWT_SECRET", "soms_dev_jwt_secret_change_me")

    def test_jwt_secret_is_string(self):
        assert isinstance(JWT_SECRET, str)
        assert len(JWT_SECRET) > 0
