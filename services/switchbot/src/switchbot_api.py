"""SwitchBot Cloud API v1.1 client with HMAC-SHA256 authentication."""

import asyncio
import base64
import hashlib
import hmac
import logging
import time
import uuid
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = "https://api.switch-bot.com/v1.1"


class RateLimiter:
    """Simple daily rate limiter (10,000 calls/day)."""

    def __init__(self, max_calls: int = 10000):
        self.max_calls = max_calls
        self._count = 0
        self._day_start = time.time()

    def check(self) -> bool:
        now = time.time()
        if now - self._day_start > 86400:
            self._count = 0
            self._day_start = now
        return self._count < self.max_calls

    def record(self):
        self._count += 1

    @property
    def remaining(self) -> int:
        return max(0, self.max_calls - self._count)


class SwitchBotAPI:
    """Async client for SwitchBot Cloud API v1.1."""

    def __init__(self, token: str, secret: str):
        self._token = token
        self._secret = secret
        self._session: aiohttp.ClientSession | None = None
        self._rate = RateLimiter()

    def _sign(self) -> dict[str, str]:
        """Generate HMAC-SHA256 auth headers."""
        t = str(int(time.time() * 1000))
        nonce = str(uuid.uuid4())
        string_to_sign = f"{self._token}{t}{nonce}"
        sign = base64.b64encode(
            hmac.new(
                self._secret.encode(),
                string_to_sign.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()
        return {
            "Authorization": self._token,
            "t": t,
            "sign": sign,
            "nonce": nonce,
            "Content-Type": "application/json",
        }

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        if not self._rate.check():
            raise RuntimeError("SwitchBot API daily rate limit reached")

        await self._ensure_session()
        url = f"{BASE_URL}{path}"
        headers = self._sign()

        kwargs: dict[str, Any] = {"headers": headers}
        if body is not None:
            kwargs["json"] = body

        async with self._session.request(method, url, **kwargs) as resp:
            self._rate.record()
            data = await resp.json()
            if resp.status != 200 or data.get("statusCode") != 100:
                logger.error(f"API error: {resp.status} {data}")
                raise RuntimeError(f"SwitchBot API error: {data.get('message', resp.status)}")
            return data.get("body", {})

    async def get_devices(self) -> dict:
        """List all devices and infrared remotes."""
        return await self._request("GET", "/devices")

    async def get_device_status(self, device_id: str) -> dict:
        """Get current status of a device."""
        return await self._request("GET", f"/devices/{device_id}/status")

    async def send_command(self, device_id: str, command: str,
                           parameter: str = "default",
                           command_type: str = "command") -> dict:
        """Send a command to a device."""
        body = {
            "command": command,
            "parameter": parameter,
            "commandType": command_type,
        }
        return await self._request("POST", f"/devices/{device_id}/commands", body)
