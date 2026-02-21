"""Unit tests for services/auth/src/user_service.py

Tests user lookup and auto-creation logic with mocked AsyncSession.
"""
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from conftest import MockResult, make_mock_db, make_user_obj, make_oauth_obj
from providers.base import OAuthUserInfo
from user_service import find_or_create_user


def _github_user_info(user_id="12345", username="octocat",
                      display_name="The Octocat", email="octo@example.com"):
    return OAuthUserInfo(
        provider="github",
        provider_user_id=user_id,
        username=username,
        display_name=display_name,
        email=email,
        avatar_url="https://avatars.example.com/octocat",
        raw_data={"id": int(user_id), "login": username},
    )


def _slack_user_info(user_id="U999", username="slackuser"):
    return OAuthUserInfo(
        provider="slack",
        provider_user_id=user_id,
        username=username,
        display_name="Slack User",
        email="slack@example.com",
        avatar_url=None,
        raw_data={"sub": user_id},
    )


class TestFindExistingOAuthAccount:

    @pytest.mark.asyncio
    async def test_returns_existing_user_and_is_not_new(self):
        """If oauth_account exists, return linked user with is_new=False."""
        user = make_user_obj(id=10, username="existing")
        oauth = make_oauth_obj(id=5, user_id=10, provider="github",
                               provider_user_id="12345")
        # execute calls: 1) find oauth_account → found
        #                2) find user by id → found
        db = make_mock_db([[oauth], [user]])

        result_user, result_oauth, is_new = await find_or_create_user(
            db, _github_user_info()
        )
        assert result_user.id == 10
        assert result_oauth.user_id == 10
        assert is_new is False

    @pytest.mark.asyncio
    async def test_updates_profile_on_existing_account(self):
        """Profile data should be refreshed on each login."""
        user = make_user_obj(id=10, username="existing")
        oauth = make_oauth_obj(id=5, user_id=10, provider="github",
                               provider_user_id="12345",
                               provider_username="old_name")
        db = make_mock_db([[oauth], [user]])

        info = _github_user_info(username="new_name", email="new@ex.com")
        await find_or_create_user(db, info)

        assert oauth.provider_username == "new_name"
        assert oauth.provider_email == "new@ex.com"


class TestCreateNewUser:

    @pytest.mark.asyncio
    async def test_creates_user_and_oauth_account(self):
        """Brand new user → create User + OAuthAccount, is_new=True."""
        # execute calls: 1) find oauth_account → not found
        #                2) find user by global_user_id → not found
        #                3) check username uniqueness → not found (available)
        db = make_mock_db([[], [], []])

        _, _, is_new = await find_or_create_user(db, _github_user_info())

        assert is_new is True
        # Should have called db.add twice (user + oauth_account)
        assert db.add.call_count == 2
        # Should have flushed to get user.id
        assert db.flush.call_count >= 1

    @pytest.mark.asyncio
    async def test_sets_correct_global_user_id(self):
        """global_user_id should be '{provider}:{provider_user_id}'."""
        db = make_mock_db([[], [], []])

        info = _github_user_info(user_id="777")
        await find_or_create_user(db, info)

        # The first db.add call should be the User
        user_arg = db.add.call_args_list[0][0][0]
        assert user_arg.global_user_id == "github:777"

    @pytest.mark.asyncio
    async def test_username_collision_appends_suffix(self):
        """If username is taken, append _1, _2, etc."""
        existing_user = make_user_obj(id=50, username="octocat")
        # execute calls: 1) oauth → not found
        #                2) global_user_id → not found
        #                3) username "octocat" → taken
        #                4) username "octocat_1" → available
        db = make_mock_db([[], [], [existing_user], []])

        await find_or_create_user(db, _github_user_info())

        user_arg = db.add.call_args_list[0][0][0]
        assert user_arg.username == "octocat_1"

    @pytest.mark.asyncio
    async def test_long_username_truncated_to_50(self):
        """Usernames longer than 50 chars are truncated."""
        long_name = "a" * 80
        db = make_mock_db([[], [], []])

        info = _github_user_info(username=long_name)
        await find_or_create_user(db, info)

        user_arg = db.add.call_args_list[0][0][0]
        assert len(user_arg.username) <= 50

    @pytest.mark.asyncio
    async def test_display_name_fallback_to_username(self):
        """If display_name is None, fall back to username."""
        db = make_mock_db([[], [], []])

        info = OAuthUserInfo(
            provider="github", provider_user_id="1", username="fallback_user",
            display_name=None, email=None, avatar_url=None, raw_data={},
        )
        await find_or_create_user(db, info)

        user_arg = db.add.call_args_list[0][0][0]
        assert user_arg.display_name == "fallback_user"


class TestExistingUserByGlobalId:

    @pytest.mark.asyncio
    async def test_links_new_oauth_to_existing_user(self):
        """If user exists by global_user_id but has no oauth_account for
        this specific provider+id combo, create only the oauth_account."""
        user = make_user_obj(id=20, username="existing",
                             global_user_id="github:12345")
        # execute calls: 1) oauth → not found
        #                2) global_user_id → found existing user
        db = make_mock_db([[], [user]])

        result_user, result_oauth, is_new = await find_or_create_user(
            db, _github_user_info()
        )
        assert result_user.id == 20
        assert is_new is False
        # Only oauth_account added (not user)
        assert db.add.call_count == 1


class TestMultiProvider:

    @pytest.mark.asyncio
    async def test_slack_user_creates_correctly(self):
        """Verify Slack provider works with the same flow."""
        db = make_mock_db([[], [], []])

        _, _, is_new = await find_or_create_user(db, _slack_user_info())

        assert is_new is True
        user_arg = db.add.call_args_list[0][0][0]
        assert user_arg.global_user_id == "slack:U999"
        assert user_arg.username == "slackuser"
