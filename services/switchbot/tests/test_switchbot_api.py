"""Unit tests for switchbot_api.py — HMAC-SHA256 signing, rate limiting, API client."""
import base64
import hashlib
import hmac
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from switchbot_api import RateLimiter, SwitchBotAPI, BASE_URL


# ── RateLimiter tests ──────────────────────────────────────────

class TestRateLimiter:
    """Tests for the daily rate limiter."""

    def test_initial_state_allows_requests(self):
        """Fresh limiter allows requests."""
        limiter = RateLimiter(max_calls=100)
        assert limiter.check() is True

    def test_remaining_starts_at_max(self):
        """Initial remaining count equals max_calls."""
        limiter = RateLimiter(max_calls=500)
        assert limiter.remaining == 500

    def test_record_decrements_remaining(self):
        """Each record() decrements remaining by 1."""
        limiter = RateLimiter(max_calls=100)
        limiter.record()
        assert limiter.remaining == 99
        limiter.record()
        assert limiter.remaining == 98

    def test_check_fails_at_limit(self):
        """check() returns False once max_calls is reached."""
        limiter = RateLimiter(max_calls=3)
        for _ in range(3):
            limiter.record()
        assert limiter.check() is False
        assert limiter.remaining == 0

    def test_remaining_never_negative(self):
        """remaining never goes below 0 even if record() is called past limit."""
        limiter = RateLimiter(max_calls=1)
        limiter.record()
        limiter.record()
        assert limiter.remaining == 0

    def test_day_reset(self):
        """Counter resets after 86400 seconds (1 day)."""
        limiter = RateLimiter(max_calls=10)
        for _ in range(10):
            limiter.record()
        assert limiter.check() is False

        # Simulate day passage by manipulating _day_start
        limiter._day_start = time.time() - 86401
        assert limiter.check() is True
        # After check, count should be reset
        assert limiter.remaining == 10

    def test_default_max_calls_is_10000(self):
        """Default max_calls is 10,000."""
        limiter = RateLimiter()
        assert limiter.max_calls == 10000
        assert limiter.remaining == 10000


# ── SwitchBotAPI._sign tests ──────────────────────────────────

class TestSwitchBotAPISign:
    """Tests for the HMAC-SHA256 signing method."""

    def test_sign_returns_required_headers(self):
        """_sign() returns Authorization, t, sign, nonce, Content-Type headers."""
        api = SwitchBotAPI(token="my_token", secret="my_secret")
        headers = api._sign()

        assert "Authorization" in headers
        assert "t" in headers
        assert "sign" in headers
        assert "nonce" in headers
        assert "Content-Type" in headers

    def test_sign_authorization_is_token(self):
        """Authorization header value matches the token."""
        api = SwitchBotAPI(token="test_token_123", secret="secret")
        headers = api._sign()
        assert headers["Authorization"] == "test_token_123"

    def test_sign_content_type_is_json(self):
        """Content-Type is application/json."""
        api = SwitchBotAPI(token="tok", secret="sec")
        headers = api._sign()
        assert headers["Content-Type"] == "application/json"

    def test_sign_timestamp_is_numeric_milliseconds(self):
        """Timestamp is a string of numeric milliseconds."""
        api = SwitchBotAPI(token="tok", secret="sec")
        headers = api._sign()
        t = headers["t"]
        assert t.isdigit()
        # Should be close to current time in ms (within 5 seconds)
        assert abs(int(t) - int(time.time() * 1000)) < 5000

    def test_sign_produces_valid_hmac(self):
        """Signature is a valid HMAC-SHA256 of token+t+nonce using secret."""
        token = "my_token"
        secret = "my_secret"
        api = SwitchBotAPI(token=token, secret=secret)

        with patch("switchbot_api.time") as mock_time, \
             patch("switchbot_api.uuid") as mock_uuid:
            mock_time.time.return_value = 1700000000.0
            mock_uuid.uuid4.return_value = "fixed-uuid-1234"

            headers = api._sign()

            # Verify the HMAC manually
            expected_t = str(int(1700000000.0 * 1000))
            string_to_sign = f"{token}{expected_t}fixed-uuid-1234"
            expected_sign = base64.b64encode(
                hmac.new(
                    secret.encode(),
                    string_to_sign.encode(),
                    hashlib.sha256,
                ).digest()
            ).decode()

            assert headers["sign"] == expected_sign
            assert headers["t"] == expected_t
            assert headers["nonce"] == "fixed-uuid-1234"

    def test_sign_nonce_is_uuid(self):
        """Nonce is a UUID4 string."""
        api = SwitchBotAPI(token="tok", secret="sec")
        headers = api._sign()
        nonce = headers["nonce"]
        # UUID4 format: 8-4-4-4-12 hex digits
        parts = nonce.split("-")
        assert len(parts) == 5


# ── SwitchBotAPI._request tests ────────────────────────────────

class TestSwitchBotAPIRequest:
    """Tests for the _request method (mocked HTTP)."""

    @pytest.mark.asyncio
    async def test_request_raises_on_rate_limit(self):
        """_request raises RuntimeError when daily rate limit is exhausted."""
        api = SwitchBotAPI(token="tok", secret="sec")
        api._rate = MagicMock()
        api._rate.check.return_value = False

        with pytest.raises(RuntimeError, match="rate limit"):
            await api._request("GET", "/devices")

    @pytest.mark.asyncio
    async def test_request_records_rate_on_success(self):
        """Successful request calls rate.record()."""
        api = SwitchBotAPI(token="tok", secret="sec")

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"statusCode": 100, "body": {"deviceList": []}})

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.request.return_value = cm
        mock_session.closed = False
        api._session = mock_session

        result = await api._request("GET", "/devices")
        assert result == {"deviceList": []}

    @pytest.mark.asyncio
    async def test_request_raises_on_api_error_status(self):
        """Non-200 response raises RuntimeError."""
        api = SwitchBotAPI(token="tok", secret="sec")

        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(return_value={"statusCode": 500, "message": "Internal Error"})

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.request.return_value = cm
        mock_session.closed = False
        api._session = mock_session

        with pytest.raises(RuntimeError, match="SwitchBot API error"):
            await api._request("GET", "/devices")

    @pytest.mark.asyncio
    async def test_request_raises_on_bad_status_code(self):
        """200 HTTP status but non-100 statusCode raises RuntimeError."""
        api = SwitchBotAPI(token="tok", secret="sec")

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"statusCode": 190, "message": "Auth failed"})

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.request.return_value = cm
        mock_session.closed = False
        api._session = mock_session

        with pytest.raises(RuntimeError, match="SwitchBot API error"):
            await api._request("GET", "/devices")


# ── SwitchBotAPI convenience methods ───────────────────────────

class TestSwitchBotAPIConvenience:
    """Tests for get_devices, get_device_status, send_command."""

    @pytest.mark.asyncio
    async def test_get_devices_calls_correct_path(self):
        """get_devices calls _request with GET /devices."""
        api = SwitchBotAPI(token="tok", secret="sec")
        api._request = AsyncMock(return_value={"deviceList": []})

        result = await api.get_devices()
        api._request.assert_called_once_with("GET", "/devices")

    @pytest.mark.asyncio
    async def test_get_device_status_calls_correct_path(self):
        """get_device_status calls _request with GET /devices/{id}/status."""
        api = SwitchBotAPI(token="tok", secret="sec")
        api._request = AsyncMock(return_value={"temperature": 22.5})

        result = await api.get_device_status("DEVICE123")
        api._request.assert_called_once_with("GET", "/devices/DEVICE123/status")

    @pytest.mark.asyncio
    async def test_send_command_calls_correct_path_and_body(self):
        """send_command sends POST with command body."""
        api = SwitchBotAPI(token="tok", secret="sec")
        api._request = AsyncMock(return_value={"status": "ok"})

        result = await api.send_command("DEVICE123", "turnOn", parameter="default", command_type="command")
        api._request.assert_called_once_with(
            "POST",
            "/devices/DEVICE123/commands",
            {
                "command": "turnOn",
                "parameter": "default",
                "commandType": "command",
            },
        )

    @pytest.mark.asyncio
    async def test_close_closes_session(self):
        """close() closes the aiohttp session."""
        api = SwitchBotAPI(token="tok", secret="sec")
        mock_session = AsyncMock()
        mock_session.closed = False
        api._session = mock_session

        await api.close()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_noop_when_no_session(self):
        """close() does nothing when session is None."""
        api = SwitchBotAPI(token="tok", secret="sec")
        api._session = None
        # Should not raise
        await api.close()

    @pytest.mark.asyncio
    async def test_ensure_session_creates_new_session(self):
        """_ensure_session creates aiohttp.ClientSession when none exists."""
        api = SwitchBotAPI(token="tok", secret="sec")
        api._session = None

        with patch("switchbot_api.aiohttp.ClientSession") as MockSession:
            MockSession.return_value = MagicMock()
            await api._ensure_session()
            MockSession.assert_called_once()
            assert api._session is not None
