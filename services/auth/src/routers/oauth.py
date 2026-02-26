import logging
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import RefreshToken
from providers import get_provider
from security import (
    create_access_token,
    create_refresh_token,
    create_state_token,
    verify_state_token,
)
from user_service import find_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth"])

SUPPORTED_PROVIDERS = ("slack", "github")


@router.get("/{provider}/login")
async def oauth_login(
    provider: str,
    redirect_uri: str = Query(None, description="Frontend callback URL"),
):
    """Start OAuth flow — redirect user to provider's authorization page."""
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    oauth_provider = get_provider(provider)
    callback_url = f"{settings.AUTH_BASE_URL}/{provider}/callback"
    state = create_state_token(nonce=os.urandom(8).hex())

    authorize_url = oauth_provider.get_authorize_url(
        redirect_uri=callback_url,
        state=state,
    )
    return RedirectResponse(url=authorize_url)


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth callback — exchange code, create/find user, issue tokens."""
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    # Verify state
    try:
        verify_state_token(state)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    # Exchange code for provider access token
    oauth_provider = get_provider(provider)
    callback_url = f"{settings.AUTH_BASE_URL}/{provider}/callback"

    try:
        provider_token = await oauth_provider.exchange_code(code, callback_url)
    except Exception as e:
        logger.error("Token exchange failed for %s: %s", provider, e)
        raise HTTPException(status_code=400, detail="Token exchange failed")

    # Get user info from provider
    try:
        user_info = await oauth_provider.get_user_info(provider_token)
    except Exception as e:
        logger.error("Failed to get user info from %s: %s", provider, e)
        raise HTTPException(status_code=400, detail="Failed to get user info")

    # Find or create user
    user, oauth_account, is_new = await find_or_create_user(db, user_info)

    # Issue tokens
    access_token, expires_in = create_access_token(
        user.id, user.username, user.display_name
    )
    raw_refresh, token_hash, family_id = create_refresh_token()

    db.add(RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        family_id=family_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.commit()

    if is_new:
        logger.info("New user registered via %s: user_id=%d", provider, user.id)

    # Redirect to frontend with tokens in fragment
    import json
    user_json = urllib.parse.quote(json.dumps({
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
    }))
    fragment = urllib.parse.urlencode({
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "expires_in": expires_in,
        "user": user_json,
    })
    redirect_url = f"{settings.FRONTEND_URL}/auth/callback#{fragment}"
    return RedirectResponse(url=redirect_url)
