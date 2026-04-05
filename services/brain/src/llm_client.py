
import asyncio
import os
import json
import re
import aiohttp
from typing import AsyncIterator, List, Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger

# Strip Qwen3.5 thinking blocks from response content
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


@dataclass
class LLMResponse:
    """Parsed LLM response."""
    content: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    raw: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class LLMClient:
    def __init__(self, api_url: str = "http://localhost:8000/v1", session: aiohttp.ClientSession = None):
        self.api_url = api_url
        self.api_key = os.getenv("OPENAI_API_KEY", "EMPTY")
        self.model = os.getenv("LLM_MODEL", "qwen3.5:9b")
        self._session = session

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
        """
        Send messages to LLM with tool definitions and parse the response.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        if tools:
            payload["tools"] = tools

        try:
            async with self._session.post(
                f"{self.api_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"LLM API Error {resp.status}: {error_text}")
                    return LLMResponse(error=f"API Error {resp.status}: {error_text}")

                raw = await resp.json()
                return self._parse_response(raw)
        except asyncio.TimeoutError:
            logger.error("LLM request timed out (120s)")
            return LLMResponse(error="Request timed out")
        except Exception as e:
            logger.error(f"LLM Connection Error: {e}")
            return LLMResponse(error=str(e))

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
    ) -> AsyncIterator[str]:
        """Stream tokens from LLM. Yields content deltas as they arrive.

        Only supports text generation (no tool calls in streaming mode).
        Strips <think>...</think> blocks on the fly.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 512,
            "stream": True,
        }
        try:
            async with self._session.post(
                f"{self.api_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"LLM stream error {resp.status}: {error_text}")
                    return

                in_think = False
                buf = ""
                async for raw_chunk in resp.content.iter_any():
                    buf += raw_chunk.decode("utf-8", errors="replace")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if not delta:
                            continue

                        # Strip <think>...</think> on the fly
                        if "<think>" in delta:
                            in_think = True
                        if in_think:
                            if "</think>" in delta:
                                after = delta.split("</think>", 1)[1]
                                in_think = False
                                if after:
                                    yield after
                            continue
                        yield delta
        except asyncio.TimeoutError:
            logger.error("LLM stream timed out (120s)")
        except Exception as e:
            logger.error(f"LLM stream error: {e}")

    def _parse_response(self, raw: Dict[str, Any]) -> LLMResponse:
        """Parse OpenAI-compatible response into LLMResponse."""
        if "error" in raw:
            return LLMResponse(error=raw["error"], raw=raw)

        choices = raw.get("choices", [])
        if not choices:
            return LLMResponse(error="No choices in response", raw=raw)

        message = choices[0].get("message", {})
        finish_reason = choices[0].get("finish_reason", "stop")
        content = message.get("content")

        # Strip Qwen3.5 <think>...</think> blocks from content
        if content:
            content = _THINK_RE.sub("", content).strip() or None

        tool_calls_raw = message.get("tool_calls", [])

        tool_calls = []
        for tc in tool_calls_raw:
            func = tc.get("function", {})
            args = func.get("arguments", "{}")
            # Handle arguments as string or dict
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            tool_calls.append({
                "id": tc.get("id", ""),
                "function": {
                    "name": func.get("name", ""),
                    "arguments": args,
                }
            })

        # Normalize finish_reason when tool_calls are present
        if tool_calls:
            finish_reason = "tool_calls"

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw=raw,
        )

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Legacy method for backward compatibility.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        if tools:
            payload["tools"] = tools

        if schema:
            payload["guided_json"] = schema

        try:
            async with self._session.post(
                f"{self.api_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"LLM API Error {resp.status}: {error_text}")

                return await resp.json()
        except Exception as e:
            logger.error(f"LLM Connection Error: {e}")
            return {"error": str(e)}
