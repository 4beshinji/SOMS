import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from config import settings


def create_access_token(user_id: int, username: str, display_name: str | None) -> tuple[str, int]:
    """Create a JWT access token. Returns (token, expires_in_seconds)."""
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "username": username,
        "display_name": display_name or username,
        "iss": "soms-auth",
        "exp": exp,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT access token."""
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        issuer="soms-auth",
    )


def create_refresh_token() -> tuple[str, str, uuid.UUID]:
    """Create a refresh token. Returns (raw_token, token_hash, family_id)."""
    raw = os.urandom(32).hex()
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    family_id = uuid.uuid4()
    return raw, token_hash, family_id


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_state_token(nonce: str) -> str:
    """Create a signed state token for OAuth CSRF protection."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {"nonce": nonce, "exp": exp}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_state_token(state: str) -> str:
    """Verify state token and return the nonce."""
    payload = jwt.decode(state, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    return payload["nonce"]
