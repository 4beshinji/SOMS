import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import settings
from database import get_db
from models import OAuthAccount, RefreshToken
from schemas import RefreshRequest, RevokeRequest, MeResponse, TokenResponse, UserInfo
from security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_refresh_token,
)
from user_service import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/token", tags=["token"])


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Rotate refresh token and issue new access token."""
    token_hash = hash_refresh_token(body.refresh_token)

    result = await db.execute(
        select(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at == None,
        )
    )
    stored = result.scalars().first()

    if not stored:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if stored.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Revoke the used token
    stored.revoked_at = datetime.now(timezone.utc)

    # Issue new refresh token in the same family
    raw_new, new_hash, _ = create_refresh_token()
    new_rt = RefreshToken(
        user_id=stored.user_id,
        token_hash=new_hash,
        family_id=stored.family_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_rt)

    # Fetch user for access token claims
    user_result = await db.execute(
        select(User).filter(User.id == stored.user_id)
    )
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token, expires_in = create_access_token(
        user.id, user.username, user.display_name
    )

    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_new,
        expires_in=expires_in,
        user=UserInfo(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
        ),
    )


@router.post("/revoke")
async def revoke_token(body: RevokeRequest, db: AsyncSession = Depends(get_db)):
    """Revoke a refresh token (logout)."""
    token_hash = hash_refresh_token(body.refresh_token)

    result = await db.execute(
        select(RefreshToken).filter(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalars().first()
    if stored and not stored.revoked_at:
        stored.revoked_at = datetime.now(timezone.utc)

        # Revoke all tokens in the same family (security measure)
        family_result = await db.execute(
            select(RefreshToken).filter(
                RefreshToken.family_id == stored.family_id,
                RefreshToken.revoked_at == None,
            )
        )
        for t in family_result.scalars().all():
            t.revoked_at = datetime.now(timezone.utc)

        await db.commit()

    return {"detail": "ok"}


@router.get("/me", response_model=MeResponse)
async def get_me(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Get current user info from access token."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[7:]
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = int(payload["sub"])

    # Fetch user
    user_result = await db.execute(select(User).filter(User.id == user_id))
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Fetch latest oauth account for avatar etc
    oauth_result = await db.execute(
        select(OAuthAccount)
        .filter(OAuthAccount.user_id == user_id)
        .order_by(OAuthAccount.created_at.desc())
        .limit(1)
    )
    oauth = oauth_result.scalars().first()

    return MeResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        provider=oauth.provider if oauth else None,
        provider_username=oauth.provider_username if oauth else None,
        provider_avatar_url=oauth.provider_avatar_url if oauth else None,
    )
