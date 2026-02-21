import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func

from database import Base
from models import OAuthAccount
from providers.base import OAuthUserInfo

logger = logging.getLogger(__name__)


# Mirror of public.users — read/write directly to dashboard's User table
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    display_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    region_id = Column(String(32), default="local")
    global_user_id = Column(String(200), nullable=True)


async def find_or_create_user(
    db: AsyncSession, info: OAuthUserInfo
) -> tuple["User", "OAuthAccount", bool]:
    """
    Look up an existing OAuth account or create a new User + OAuthAccount.
    Returns (user, oauth_account, is_new_user).
    """
    # 1. Check if oauth_account already exists
    result = await db.execute(
        select(OAuthAccount).filter(
            OAuthAccount.provider == info.provider,
            OAuthAccount.provider_user_id == info.provider_user_id,
        )
    )
    existing_oauth = result.scalars().first()

    if existing_oauth:
        # Update profile data
        existing_oauth.provider_username = info.username
        existing_oauth.provider_email = info.email
        existing_oauth.provider_avatar_url = info.avatar_url
        existing_oauth.provider_data = info.raw_data

        user_result = await db.execute(
            select(User).filter(User.id == existing_oauth.user_id)
        )
        user = user_result.scalars().first()
        return user, existing_oauth, False

    # 2. Check if a user with matching global_user_id exists
    global_id = f"{info.provider}:{info.provider_user_id}"
    user_result = await db.execute(
        select(User).filter(User.global_user_id == global_id)
    )
    user = user_result.scalars().first()

    is_new = False
    if not user:
        # 3. Create new user in public.users
        # Generate a unique username
        base_username = info.username[:50]
        username = base_username
        suffix = 1
        while True:
            check = await db.execute(
                select(User).filter(User.username == username)
            )
            if not check.scalars().first():
                break
            username = f"{base_username}_{suffix}"
            suffix += 1

        user = User(
            username=username,
            display_name=info.display_name or info.username,
            is_active=True,
            global_user_id=global_id,
        )
        db.add(user)
        await db.flush()  # get user.id
        is_new = True
        logger.info("Created new user: id=%d username=%s via %s", user.id, username, info.provider)

    # 4. Create oauth_account
    oauth_account = OAuthAccount(
        user_id=user.id,
        provider=info.provider,
        provider_user_id=info.provider_user_id,
        provider_username=info.username,
        provider_email=info.email,
        provider_avatar_url=info.avatar_url,
        provider_data=info.raw_data,
    )
    db.add(oauth_account)
    await db.flush()

    return user, oauth_account, is_new
