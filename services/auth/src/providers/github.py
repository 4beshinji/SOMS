import urllib.parse
import httpx
from providers.base import OAuthProvider, OAuthUserInfo
from config import settings


class GitHubProvider(OAuthProvider):
    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USERINFO_URL = "https://api.github.com/user"

    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": "read:user user:email",
        }
        return f"{self.AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise ValueError(f"GitHub token exchange failed: {data['error_description']}")
            return data["access_token"]

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                self.USERINFO_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            # Fetch primary email if not public
            email = data.get("email")
            if not email:
                email_resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                if email_resp.status_code == 200:
                    emails = email_resp.json()
                    for e in emails:
                        if e.get("primary"):
                            email = e["email"]
                            break

        return OAuthUserInfo(
            provider="github",
            provider_user_id=str(data["id"]),
            username=data["login"],
            display_name=data.get("name") or data["login"],
            email=email,
            avatar_url=data.get("avatar_url"),
            raw_data=data,
        )
