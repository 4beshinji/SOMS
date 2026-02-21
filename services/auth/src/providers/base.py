from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class OAuthUserInfo:
    provider: str
    provider_user_id: str
    username: str
    display_name: Optional[str]
    email: Optional[str]
    avatar_url: Optional[str]
    raw_data: Dict[str, Any]


class OAuthProvider(ABC):
    @abstractmethod
    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        """Build the provider's authorization URL."""

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> str:
        """Exchange authorization code for access token."""

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Fetch user profile from provider API."""
