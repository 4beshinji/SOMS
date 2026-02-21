"""JWT authentication middleware for wallet service.

Provides optional and required auth dependencies for FastAPI endpoints.
- get_current_user(): returns AuthUser | None (backward-compatible, allows unauthenticated)
- require_auth(): returns AuthUser (raises 401 if no valid token)
"""

import os
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Header

JWT_SECRET = os.getenv("JWT_SECRET", "soms_dev_jwt_secret_change_me")
JWT_ALGORITHM = "HS256"


@dataclass
class AuthUser:
    id: int
    username: str
    display_name: str


async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> Optional[AuthUser]:
    """Extract user from JWT. Returns None if no token (backward-compatible)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], issuer="soms-auth")
        return AuthUser(
            id=payload["sub"],
            username=payload.get("username", ""),
            display_name=payload.get("display_name", ""),
        )
    except jwt.PyJWTError:
        return None


async def require_auth(
    user: Optional[AuthUser] = Depends(get_current_user),
) -> AuthUser:
    """Require a valid JWT. Raises 401 if missing or invalid."""
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
