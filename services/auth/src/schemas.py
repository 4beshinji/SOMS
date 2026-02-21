from pydantic import BaseModel
from typing import Optional


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserInfo"


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class RevokeRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    provider: Optional[str] = None
    provider_username: Optional[str] = None
    provider_avatar_url: Optional[str] = None
