"""Tests for VLM client — image encoding, API calls, error handling."""
import base64
import json
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vlm.vlm_client import VLMClient, VLMResponse, VGA_SIZE

# Note: cv2 may be mocked by conftest.py (for tracking tests).
# encode_frame tests are skipped when cv2 is mocked; API tests
# patch encode_frame directly to avoid cv2 dependency.

_FAKE_B64 = base64.b64encode(b"fake-jpeg-data").decode("utf-8")


def _cv2_is_real():
    import cv2
    return not isinstance(cv2.imencode, MagicMock)


# --- encode_frame tests (only when real cv2 is available) ---

@pytest.mark.skipif(not _cv2_is_real(), reason="cv2 is mocked by conftest")
class TestEncodeFrame:
    def test_returns_valid_base64(self):
        from vlm.vlm_client import encode_frame
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        b64 = encode_frame(img)
        decoded = base64.b64decode(b64)
        assert len(decoded) > 0

    def test_resizes_to_vga(self):
        from vlm.vlm_client import encode_frame
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        b64 = encode_frame(img)
        decoded = base64.b64decode(b64)
        assert decoded[:2] == b'\xff\xd8'  # JPEG magic bytes

    def test_small_image_resized(self):
        from vlm.vlm_client import encode_frame
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        b64 = encode_frame(img)
        decoded = base64.b64decode(b64)
        assert decoded[:2] == b'\xff\xd8'

    def test_vga_image_not_resized_still_valid(self):
        from vlm.vlm_client import encode_frame
        img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        b64 = encode_frame(img)
        assert len(b64) > 100


# --- VLMClient tests ---

class TestVLMClient:
    def test_init_defaults(self):
        client = VLMClient(api_url="http://localhost:11434", model="qwen3-vl:8b")
        assert client.api_url == "http://localhost:11434"
        assert client.model == "qwen3-vl:8b"
        assert client.timeout_sec == 30
        assert client.api_style == "ollama"

    def test_init_strips_trailing_slash(self):
        client = VLMClient(api_url="http://localhost:11434/", model="test")
        assert client.api_url == "http://localhost:11434"

    def test_init_openai_style(self):
        client = VLMClient(
            api_url="http://localhost:8000",
            model="qwen3.5",
            api_style="openai",
        )
        assert client.api_style == "openai"


class TestVLMClientOllamaCall:
    @pytest.mark.asyncio
    @patch("vlm.vlm_client.encode_frame", return_value=_FAKE_B64)
    async def test_successful_ollama_call(self, _mock_encode):
        client = VLMClient(api_url="http://test:11434", model="qwen3-vl:8b")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "message": {"content": "オフィスに2人います"},
            "model": "qwen3-vl:8b",
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client._session = mock_session

        img = np.zeros((480, 640, 3), dtype=np.uint8)
        result = await client.analyze(img, "describe this")

        assert isinstance(result, VLMResponse)
        assert result.content == "オフィスに2人います"
        assert result.error is None
        assert result.latency_sec > 0

    @pytest.mark.asyncio
    @patch("vlm.vlm_client.encode_frame", return_value=_FAKE_B64)
    async def test_ollama_http_error(self, _mock_encode):
        client = VLMClient(api_url="http://test:11434", model="test")

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client._session = mock_session

        img = np.zeros((480, 640, 3), dtype=np.uint8)
        result = await client.analyze(img, "test")

        assert result.error is not None
        assert "500" in result.error


class TestVLMClientOpenAICall:
    @pytest.mark.asyncio
    @patch("vlm.vlm_client.encode_frame", return_value=_FAKE_B64)
    async def test_successful_openai_call(self, _mock_encode):
        client = VLMClient(
            api_url="http://test:8000", model="qwen3.5", api_style="openai"
        )

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "choices": [{"message": {"content": "Scene description"}}],
            "model": "qwen3.5",
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        client._session = mock_session

        img = np.zeros((480, 640, 3), dtype=np.uint8)
        result = await client.analyze(img, "describe")

        assert result.content == "Scene description"
        assert result.error is None


class TestVLMClientConnectionError:
    @pytest.mark.asyncio
    @patch("vlm.vlm_client.encode_frame", return_value=_FAKE_B64)
    async def test_connection_error(self, _mock_encode):
        import aiohttp

        client = VLMClient(api_url="http://test:11434", model="test")

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("Connection refused"))
        mock_session.closed = False
        client._session = mock_session

        img = np.zeros((480, 640, 3), dtype=np.uint8)
        result = await client.analyze(img, "test")

        assert result.error is not None
        assert "Connection refused" in result.error


class TestVLMClientClose:
    @pytest.mark.asyncio
    async def test_close_session(self):
        client = VLMClient(api_url="http://test:11434", model="test")
        mock_session = AsyncMock()
        mock_session.closed = False
        client._session = mock_session

        await client.close()
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_no_session(self):
        client = VLMClient(api_url="http://test:11434", model="test")
        await client.close()  # Should not raise
