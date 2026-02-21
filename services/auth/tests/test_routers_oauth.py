"""Unit tests for services/auth/src/routers/oauth.py

Tests OAuth login redirect and callback endpoints via FastAPI TestClient.
Uses a test app (no lifespan) with mocked DB and providers.
"""
import urllib.parse
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import make_mock_db, make_user_obj, make_oauth_obj
from database import get_db
from routers import oauth
from providers.base import OAuthUserInfo
from config import settings


def _create_test_app(db_mock=None):
    app = FastAPI()
    app.include_router(oauth.router)
    if db_mock is not None:
        app.dependency_overrides[get_db] = lambda: db_mock
    return app


class TestOAuthLogin:

    def test_slack_login_redirects(self):
        app = _create_test_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/slack/login")
        assert resp.status_code == 307
        location = resp.headers["location"]
        assert "slack.com/openid/connect/authorize" in location

    def test_github_login_redirects(self):
        app = _create_test_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/github/login")
        assert resp.status_code == 307
        location = resp.headers["location"]
        assert "github.com/login/oauth/authorize" in location

    def test_unsupported_provider_returns_400(self):
        app = _create_test_app()
        client = TestClient(app)
        resp = client.get("/facebook/login")
        assert resp.status_code == 400
        assert "Unsupported provider" in resp.json()["detail"]

    def test_redirect_url_contains_state_param(self):
        app = _create_test_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/slack/login")
        location = resp.headers["location"]
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
        assert "state" in parsed
        assert len(parsed["state"][0]) > 10  # signed JWT, not empty

    def test_redirect_url_contains_callback_url(self):
        app = _create_test_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/github/login")
        location = resp.headers["location"]
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
        callback = parsed["redirect_uri"][0]
        assert "/github/callback" in callback


class TestOAuthCallback:

    def test_unsupported_provider_returns_400(self):
        app = _create_test_app(make_mock_db())
        client = TestClient(app)
        resp = client.get("/twitter/callback", params={"code": "c", "state": "s"})
        assert resp.status_code == 400

    def test_invalid_state_returns_400(self):
        app = _create_test_app(make_mock_db())
        client = TestClient(app)
        resp = client.get("/github/callback",
                          params={"code": "c", "state": "invalid_garbage"})
        assert resp.status_code == 400
        assert "Invalid or expired state" in resp.json()["detail"]

    def test_token_exchange_failure_returns_400(self):
        from security import create_state_token
        state = create_state_token("testnonce")

        mock_provider = MagicMock()
        mock_provider.exchange_code = AsyncMock(side_effect=Exception("network error"))

        db = make_mock_db()
        app = _create_test_app(db)
        client = TestClient(app)

        with patch("routers.oauth.get_provider", return_value=mock_provider):
            resp = client.get("/github/callback",
                              params={"code": "bad", "state": state})

        assert resp.status_code == 400
        assert "Token exchange failed" in resp.json()["detail"]

    def test_userinfo_failure_returns_400(self):
        from security import create_state_token
        state = create_state_token("testnonce")

        mock_provider = MagicMock()
        mock_provider.exchange_code = AsyncMock(return_value="access_tok")
        mock_provider.get_user_info = AsyncMock(side_effect=Exception("api error"))

        db = make_mock_db()
        app = _create_test_app(db)
        client = TestClient(app)

        with patch("routers.oauth.get_provider", return_value=mock_provider):
            resp = client.get("/github/callback",
                              params={"code": "c", "state": state})

        assert resp.status_code == 400
        assert "Failed to get user info" in resp.json()["detail"]

    def test_successful_callback_redirects_with_tokens(self):
        from security import create_state_token
        state = create_state_token("testnonce")

        mock_provider = MagicMock()
        mock_provider.exchange_code = AsyncMock(return_value="provider_tok")
        mock_provider.get_user_info = AsyncMock(return_value=OAuthUserInfo(
            provider="github", provider_user_id="42", username="octocat",
            display_name="Octo", email="o@ex.com", avatar_url=None, raw_data={},
        ))

        user = make_user_obj(id=7, username="octocat", display_name="Octo")
        oauth_acc = make_oauth_obj(user_id=7)

        with patch("routers.oauth.find_or_create_user",
                   new_callable=AsyncMock,
                   return_value=(user, oauth_acc, True)):
            db = make_mock_db()
            app = _create_test_app(db)
            client = TestClient(app, follow_redirects=False)

            with patch("routers.oauth.get_provider", return_value=mock_provider):
                resp = client.get("/github/callback",
                                  params={"code": "valid", "state": state})

        assert resp.status_code == 307
        location = resp.headers["location"]
        assert settings.FRONTEND_URL in location
        assert "/auth/callback#" in location
        # Fragment should contain access_token and refresh_token
        fragment = location.split("#")[1]
        params = urllib.parse.parse_qs(fragment)
        assert "access_token" in params
        assert "refresh_token" in params
        assert "expires_in" in params
        assert "user" in params
