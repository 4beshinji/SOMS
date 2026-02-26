from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from jwt_auth import AuthUser, require_service_auth
from models import LedgerEntry
from schemas import WalletCreate, WalletResponse, LedgerEntryResponse
from services.ledger import get_or_create_wallet, SYSTEM_USER_ID
from jwt_auth import AuthUser, get_current_user

router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.post("/", response_model=WalletResponse)
async def create_wallet(body: WalletCreate, db: AsyncSession = Depends(get_db), _auth: AuthUser = Depends(require_service_auth)):
    wallet = await get_or_create_wallet(db, body.user_id)
    await db.commit()
    await db.refresh(wallet)
    return wallet


@router.get("/{user_id}", response_model=WalletResponse)
async def get_wallet(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    auth_user: Optional[AuthUser] = Depends(get_current_user),
):
    # If authenticated, users may only view their own wallet or the system wallet
    if auth_user and user_id != auth_user.id and user_id != SYSTEM_USER_ID:
        raise HTTPException(status_code=403, detail="Access denied")
    wallet = await get_or_create_wallet(db, user_id)
    await db.commit()
    return wallet


@router.get("/{user_id}/history", response_model=list[LedgerEntryResponse])
async def get_history(
    user_id: int,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth_user: Optional[AuthUser] = Depends(get_current_user),
):
    if auth_user and user_id != auth_user.id and user_id != SYSTEM_USER_ID:
        raise HTTPException(status_code=403, detail="Access denied")
    wallet = await get_or_create_wallet(db, user_id)
    await db.commit()

    entries = await db.execute(
        select(LedgerEntry)
        .filter(LedgerEntry.wallet_id == wallet.id)
        .order_by(LedgerEntry.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return entries.scalars().all()
