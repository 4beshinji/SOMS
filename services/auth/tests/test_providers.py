"""Unit tests for OAuth providers (Slack, GitHub).

All HTTP calls are mocked — no real network access.
"""
import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers import get_provider, PROVIDERS
from providers.slack import SlackProvider
from providers.github import GitHubProvider
from providers.base import OAuthUserInfo
from config import settings


# ── Provider Registry ────────────────────────────────────────────


class TestProviderRegistry:

    def test_get_slack_provider(self):
        p = get_provider("slack")
        assert isinstance(p, SlackProvider)

    def test_get_github_provider(self):
        p = get_provider("github")
        assert isinstance(p, GitHubProvider)

    def test_get_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("facebook")

    def test_registry_has_both_providers(self):
        assert set(PROVIDERS.keys()) == {"slack", "github"}


# ── Slack Provider ───────────────────────────────────────────────


class TestSlackAuthorizeUrl:

    def test_starts_with_slack_url(self):
        url = SlackProvider().get_authorize_url("https://cb", "state123")
        assert url.startswith("https://slack.com/openid/connect/authorize?")

    def test_contains_required_params(self):
        url = SlackProvider().get_authorize_url("https://cb/callback", "mystate")
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert parsed["client_id"] == [settings.SLACK_CLIENT_ID]
        assert parsed["response_type"] == ["code"]
        assert parsed["redirect_uri"] == ["https://cb/callback"]
        assert parsed["state"] == ["mystate"]

    def test_scopes_include_openid_profile_email(self):
        url = SlackProvider().get_authorize_url("https://cb", "s")
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        scopes = parsed["scope"][0].split()
        assert "openid" in scopes
        assert "profile" in scopes
        assert "email" in scopes


class TestSlackExchangeCode:

    @pytest.mark.asyncio
    async def test_success_returns_access_token(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "access_token": "xoxp-slack-token"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.slack.httpx.AsyncClient", return_value=mock_client):
            token = await SlackProvider().exchange_code("code123", "https://cb")
            assert token == "xoxp-slack-token"

    @pytest.mark.asyncio
    async def test_error_response_raises_value_error(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "error": "invalid_code"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.slack.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="invalid_code"):
                await SlackProvider().exchange_code("bad_code", "https://cb")

    @pytest.mark.asyncio
    async def test_sends_correct_post_data(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "access_token": "tok"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.slack.httpx.AsyncClient", return_value=mock_client):
            await SlackProvider().exchange_code("mycode", "https://redirect")

        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["data"]["code"] == "mycode"
        assert call_kwargs.kwargs["data"]["redirect_uri"] == "https://redirect"
        assert call_kwargs.kwargs["data"]["grant_type"] == "authorization_code"


class TestSlackGetUserInfo:

    @pytest.mark.asyncio
    async def test_success_returns_oauth_user_info(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "sub": "U12345",
            "name": "Alice",
            "email": "alice@example.com",
            "picture": "https://avatar.example.com/alice.jpg",
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.slack.httpx.AsyncClient", return_value=mock_client):
            info = await SlackProvider().get_user_info("xoxp-token")

        assert isinstance(info, OAuthUserInfo)
        assert info.provider == "slack"
        assert info.provider_user_id == "U12345"
        assert info.username == "Alice"
        assert info.email == "alice@example.com"
        assert info.avatar_url == "https://avatar.example.com/alice.jpg"

    @pytest.mark.asyncio
    async def test_error_response_raises(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "error": "token_revoked"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.slack.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="token_revoked"):
                await SlackProvider().get_user_info("bad_token")

    @pytest.mark.asyncio
    async def test_missing_name_uses_sub_as_username(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "sub": "U99"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.slack.httpx.AsyncClient", return_value=mock_client):
            info = await SlackProvider().get_user_info("tok")
        assert info.username == "U99"


# ── GitHub Provider ──────────────────────────────────────────────


class TestGitHubAuthorizeUrl:

    def test_starts_with_github_url(self):
        url = GitHubProvider().get_authorize_url("https://cb", "state1")
        assert url.startswith("https://github.com/login/oauth/authorize?")

    def test_contains_required_params(self):
        url = GitHubProvider().get_authorize_url("https://cb/callback", "state2")
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert parsed["client_id"] == [settings.GITHUB_CLIENT_ID]
        assert parsed["redirect_uri"] == ["https://cb/callback"]
        assert parsed["state"] == ["state2"]

    def test_scopes_include_read_user_and_email(self):
        url = GitHubProvider().get_authorize_url("https://cb", "s")
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        scopes = parsed["scope"][0].split()
        assert "read:user" in scopes
        assert "user:email" in scopes


class TestGitHubExchangeCode:

    @pytest.mark.asyncio
    async def test_success_returns_access_token(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "gho_github_token"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.github.httpx.AsyncClient", return_value=mock_client):
            token = await GitHubProvider().exchange_code("code456", "https://cb")
            assert token == "gho_github_token"

    @pytest.mark.asyncio
    async def test_error_response_raises_value_error(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "error": "bad_verification_code",
            "error_description": "The code passed is incorrect",
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.github.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="incorrect"):
                await GitHubProvider().exchange_code("bad", "https://cb")

    @pytest.mark.asyncio
    async def test_sends_accept_json_header(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "tok"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.github.httpx.AsyncClient", return_value=mock_client):
            await GitHubProvider().exchange_code("c", "https://cb")

        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["headers"]["Accept"] == "application/json"


class TestGitHubGetUserInfo:

    @pytest.mark.asyncio
    async def test_success_with_public_email(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": 42,
            "login": "octocat",
            "name": "The Octocat",
            "email": "octocat@github.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/42",
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.github.httpx.AsyncClient", return_value=mock_client):
            info = await GitHubProvider().get_user_info("gho_token")

        assert info.provider == "github"
        assert info.provider_user_id == "42"
        assert info.username == "octocat"
        assert info.display_name == "The Octocat"
        assert info.email == "octocat@github.com"

    @pytest.mark.asyncio
    async def test_private_email_fetches_from_emails_api(self):
        # First call: /user (no email)
        user_resp = MagicMock()
        user_resp.json.return_value = {
            "id": 7, "login": "secretcat", "name": "Secret Cat",
            "email": None, "avatar_url": "https://a.com/7",
        }
        user_resp.raise_for_status = MagicMock()

        # Second call: /user/emails
        email_resp = MagicMock()
        email_resp.status_code = 200
        email_resp.json.return_value = [
            {"email": "noreply@users.github.com", "primary": False},
            {"email": "secret@real.com", "primary": True},
        ]

        mock_client = AsyncMock()
        mock_client.get.side_effect = [user_resp, email_resp]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.github.httpx.AsyncClient", return_value=mock_client):
            info = await GitHubProvider().get_user_info("tok")

        assert info.email == "secret@real.com"

    @pytest.mark.asyncio
    async def test_email_api_failure_returns_none_email(self):
        user_resp = MagicMock()
        user_resp.json.return_value = {
            "id": 8, "login": "nomail", "name": None,
            "email": None, "avatar_url": None,
        }
        user_resp.raise_for_status = MagicMock()

        email_resp = MagicMock()
        email_resp.status_code = 403  # forbidden

        mock_client = AsyncMock()
        mock_client.get.side_effect = [user_resp, email_resp]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.github.httpx.AsyncClient", return_value=mock_client):
            info = await GitHubProvider().get_user_info("tok")

        assert info.email is None

    @pytest.mark.asyncio
    async def test_no_name_uses_login_as_display_name(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": 9, "login": "nameless", "name": None,
            "email": "x@x.com", "avatar_url": None,
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("providers.github.httpx.AsyncClient", return_value=mock_client):
            info = await GitHubProvider().get_user_info("tok")

        assert info.display_name == "nameless"
