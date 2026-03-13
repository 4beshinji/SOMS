"""
VLM (Vision Language Model) async client.
Supports Ollama native API and OpenAI-compatible API (vLLM etc).
"""
import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
import cv2
import numpy as np

logger = logging.getLogger(__name__)

VGA_SIZE = (640, 480)
JPEG_QUALITY = 80


@dataclass
class VLMResponse:
    content: str = ""
    model: str = ""
    latency_sec: float = 0.0
    error: Optional[str] = None


def encode_frame(image: np.ndarray) -> str:
    """Resize to VGA, JPEG-encode, and return base64 string."""
    h, w = image.shape[:2]
    if w != VGA_SIZE[0] or h != VGA_SIZE[1]:
        image = cv2.resize(image, VGA_SIZE, interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return base64.b64encode(buf.tobytes()).decode("utf-8")


class VLMClient:
    """Async VLM client supporting Ollama and OpenAI-compatible APIs."""

    def __init__(
        self,
        api_url: str,
        model: str,
        timeout_sec: float = 30,
        api_style: str = "ollama",
    ):
        self.api_url = api_url.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec
        self.api_style = api_style
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_sec)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def analyze(
        self,
        image: np.ndarray,
        prompt: str,
        max_tokens: int = 512,
    ) -> VLMResponse:
        """Send an image + prompt to the VLM and return the response."""
        t0 = time.time()
        b64 = encode_frame(image)

        try:
            if self.api_style == "openai":
                return await self._call_openai(b64, prompt, max_tokens, t0)
            else:
                return await self._call_ollama(b64, prompt, max_tokens, t0)
        except aiohttp.ClientError as e:
            latency = time.time() - t0
            logger.error("VLM request failed: %s", e)
            return VLMResponse(error=str(e), latency_sec=latency, model=self.model)
        except Exception as e:
            latency = time.time() - t0
            logger.error("VLM unexpected error: %s", e)
            return VLMResponse(error=str(e), latency_sec=latency, model=self.model)

    async def _call_ollama(
        self, b64: str, prompt: str, max_tokens: int, t0: float
    ) -> VLMResponse:
        url = f"{self.api_url}/api/chat"
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64],
                }
            ],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        session = self._get_session()
        async with session.post(url, json=body) as resp:
            if resp.status != 200:
                text = await resp.text()
                return VLMResponse(
                    error=f"HTTP {resp.status}: {text[:200]}",
                    latency_sec=time.time() - t0,
                    model=self.model,
                )
            data = await resp.json()
            content = data.get("message", {}).get("content", "")
            return VLMResponse(
                content=content,
                model=data.get("model", self.model),
                latency_sec=time.time() - t0,
            )

    async def _call_openai(
        self, b64: str, prompt: str, max_tokens: int, t0: float
    ) -> VLMResponse:
        url = f"{self.api_url}/v1/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "stream": False,
        }
        session = self._get_session()
        async with session.post(url, json=body) as resp:
            if resp.status != 200:
                text = await resp.text()
                return VLMResponse(
                    error=f"HTTP {resp.status}: {text[:200]}",
                    latency_sec=time.time() - t0,
                    model=self.model,
                )
            data = await resp.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return VLMResponse(
                content=content,
                model=data.get("model", self.model),
                latency_sec=time.time() - t0,
            )

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
