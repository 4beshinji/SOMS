import urllib.parse
import httpx
from providers.base import OAuthProvider, OAuthUserInfo
from config import settings


class SlackProvider(OAuthProvider):
    AUTHORIZE_URL = "https://slack.com/openid/connect/authorize"
    TOKEN_URL = "https://slack.com/api/openid.connect.token"
    USERINFO_URL = "https://slack.com/api/openid.connect.userInfo"

    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": settings.SLACK_CLIENT_ID,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": state,  # reuse state as nonce for simplicity
        }
        return f"{self.AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": settings.SLACK_CLIENT_ID,
                    "client_secret": settings.SLACK_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok", False):
                raise ValueError(f"Slack token exchange failed: {data.get('error')}")
            return data["access_token"]

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok", False):
                raise ValueError(f"Slack userinfo failed: {data.get('error')}")

        return OAuthUserInfo(
            provider="slack",
            provider_user_id=data["sub"],
            username=data.get("name", data["sub"]),
            display_name=data.get("name"),
            email=data.get("email"),
            avatar_url=data.get("picture"),
            raw_data=data,
        )
