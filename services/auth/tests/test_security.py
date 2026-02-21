"""Unit tests for services/auth/src/security.py

Covers JWT access tokens, refresh tokens, and OAuth state tokens.
"""
import hashlib
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest

from security import (
    create_access_token,
    decode_access_token,
    create_refresh_token,
    hash_refresh_token,
    create_state_token,
    verify_state_token,
)
from config import settings


# ── Access Token ─────────────────────────────────────────────────


class TestCreateAccessToken:

    def test_returns_token_and_expiry(self):
        token, expires_in = create_access_token(42, "alice", "Alice A")
        assert isinstance(token, str) and len(token) > 0
        assert expires_in == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    def test_token_contains_correct_claims(self):
        token, _ = create_access_token(7, "bob", "Bob B")
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        assert payload["sub"] == "7"
        assert payload["username"] == "bob"
        assert payload["display_name"] == "Bob B"
        assert payload["iss"] == "soms-auth"
        assert "exp" in payload
        assert "iat" in payload

    def test_none_display_name_falls_back_to_username(self):
        token, _ = create_access_token(1, "charlie", None)
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        assert payload["display_name"] == "charlie"

    def test_empty_display_name_falls_back_to_username(self):
        token, _ = create_access_token(1, "dave", "")
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        # empty string is falsy → falls back to username
        assert payload["display_name"] == "dave"

    def test_expiry_is_in_the_future(self):
        token, _ = create_access_token(1, "u", "U")
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)

    def test_different_users_produce_different_tokens(self):
        t1, _ = create_access_token(1, "a", "A")
        t2, _ = create_access_token(2, "b", "B")
        assert t1 != t2


class TestDecodeAccessToken:

    def test_roundtrip(self):
        token, _ = create_access_token(99, "zara", "Zara Z")
        payload = decode_access_token(token)
        assert payload["sub"] == "99"
        assert payload["username"] == "zara"

    def test_expired_token_raises(self):
        payload = {
            "sub": "1", "username": "x", "display_name": "X",
            "iss": "soms-auth",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
            "iat": datetime.now(timezone.utc) - timedelta(minutes=20),
        }
        token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_wrong_secret_raises(self):
        token, _ = create_access_token(1, "u", "U")
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, "wrong_secret", algorithms=["HS256"])

    def test_wrong_issuer_raises(self):
        payload = {
            "sub": "1", "username": "x", "display_name": "X",
            "iss": "not-soms",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
        with pytest.raises(jwt.InvalidIssuerError):
            decode_access_token(token)

    def test_tampered_token_raises(self):
        token, _ = create_access_token(1, "u", "U")
        # Flip a character in the signature portion
        parts = token.split(".")
        sig = parts[2]
        tampered_char = "A" if sig[0] != "A" else "B"
        parts[2] = tampered_char + sig[1:]
        tampered = ".".join(parts)
        with pytest.raises(jwt.InvalidSignatureError):
            decode_access_token(tampered)

    def test_malformed_token_raises(self):
        with pytest.raises(jwt.DecodeError):
            decode_access_token("not.a.real.token")


# ── Refresh Token ────────────────────────────────────────────────


class TestRefreshToken:

    def test_create_returns_three_values(self):
        raw, token_hash, family_id = create_refresh_token()
        assert isinstance(raw, str)
        assert isinstance(token_hash, str)
        assert len(raw) == 64  # 32 bytes hex
        assert len(token_hash) == 64  # SHA-256 hex

    def test_hash_matches_raw(self):
        raw, token_hash, _ = create_refresh_token()
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert token_hash == expected

    def test_unique_tokens_on_each_call(self):
        results = [create_refresh_token() for _ in range(5)]
        raws = [r[0] for r in results]
        hashes = [r[1] for r in results]
        families = [r[2] for r in results]
        assert len(set(raws)) == 5
        assert len(set(hashes)) == 5
        assert len(set(families)) == 5

    def test_hash_refresh_token_deterministic(self):
        assert hash_refresh_token("abc123") == hash_refresh_token("abc123")

    def test_hash_refresh_token_different_inputs(self):
        assert hash_refresh_token("aaa") != hash_refresh_token("bbb")

    def test_hash_matches_hashlib_sha256(self):
        raw = "test_token_value"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert hash_refresh_token(raw) == expected


# ── State Token (CSRF) ──────────────────────────────────────────


class TestStateToken:

    def test_roundtrip(self):
        nonce = "abcdef1234"
        state = create_state_token(nonce)
        recovered = verify_state_token(state)
        assert recovered == nonce

    def test_expired_state_raises(self):
        # Create a state that expired 1 minute ago
        payload = {
            "nonce": "old",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
        state = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_state_token(state)

    def test_tampered_state_raises(self):
        state = create_state_token("test")
        parts = state.split(".")
        tampered_char = "X" if parts[1][0] != "X" else "Y"
        parts[1] = tampered_char + parts[1][1:]
        tampered = ".".join(parts)
        with pytest.raises(Exception):  # DecodeError or InvalidSignatureError
            verify_state_token(tampered)

    def test_state_with_wrong_secret_raises(self):
        payload = {
            "nonce": "secret_nonce",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        }
        state = jwt.encode(payload, "wrong_key", algorithm="HS256")
        with pytest.raises(jwt.InvalidSignatureError):
            verify_state_token(state)
