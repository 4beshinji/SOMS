"""
Chat HTTP server — ephemeral Q&A endpoint inside the Brain container.
Runs alongside the main MQTT-based cognitive loop on port 8080.

Also serves Ollama model management endpoints (list / pull / delete).
"""
import json
import os

import aiohttp
from aiohttp import web
from loguru import logger

from chat_prompt import build_chat_system_message, CHAT_TOOLS, build_cleanup_prompt
from llm_client import LLMClient

CHAT_MAX_ITERATIONS = 3
CHAT_MAX_RESPONSE_CHARS = int(os.getenv("CHAT_MAX_RESPONSE_CHARS", "80"))
VOICE_SERVICE_URL = os.getenv("VOICE_SERVICE_URL", "http://voice-service:8000")
CLEANUP_MODEL = os.getenv("CHAT_CLEANUP_MODEL", "")
LLM_API_URL = os.getenv("LLM_API_URL", "http://mock-llm:8000/v1")
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")


def create_chat_app(brain) -> web.Application:
    """Factory: create aiohttp app with access to Brain components."""
    app = web.Application()

    async def handle_chat(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        user_message = data.get("user_message", "").strip()
        if not user_message:
            return web.json_response({"error": "Empty message"}, status=400)

        try:
            result = await _process_chat(brain, user_message)
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Chat processing error: {e}")
            return web.json_response(
                {"content": "ごめん、ちょっとエラーが出た", "audio_url": None},
                status=200,
            )

    async def handle_health(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "brain-chat"})

    async def handle_models_list(request: web.Request) -> web.Response:
        """List models available in Ollama."""
        try:
            async with brain._session.get(
                f"{OLLAMA_BASE_URL}/api/tags",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return web.json_response(data)
                return web.json_response(
                    {"error": f"Ollama returned {resp.status}"}, status=502
                )
        except Exception as e:
            return web.json_response({"error": str(e)}, status=502)

    async def handle_models_pull(request: web.Request) -> web.StreamResponse:
        """Pull a model from Ollama. Streams progress as NDJSON."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        model_name = data.get("name", "").strip()
        if not model_name:
            return web.json_response({"error": "Missing 'name'"}, status=400)

        logger.info(f"Pulling Ollama model: {model_name}")

        try:
            resp = web.StreamResponse(
                status=200,
                reason="OK",
                headers={"Content-Type": "application/x-ndjson"},
            )
            await resp.prepare(request)

            async with brain._session.post(
                f"{OLLAMA_BASE_URL}/api/pull",
                json={"name": model_name, "stream": True},
                timeout=aiohttp.ClientTimeout(total=3600),
            ) as ollama_resp:
                if ollama_resp.status != 200:
                    error_text = await ollama_resp.text()
                    await resp.write(
                        json.dumps({"error": error_text}).encode() + b"\n"
                    )
                    await resp.write_eof()
                    return resp

                async for line in ollama_resp.content:
                    if line:
                        await resp.write(line)

            await resp.write_eof()
            logger.info(f"Model pull complete: {model_name}")
            return resp
        except Exception as e:
            logger.error(f"Model pull error: {e}")
            return web.json_response({"error": str(e)}, status=502)

    async def handle_models_delete(request: web.Request) -> web.Response:
        """Delete a model from Ollama."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        model_name = data.get("name", "").strip()
        if not model_name:
            return web.json_response({"error": "Missing 'name'"}, status=400)

        try:
            async with brain._session.delete(
                f"{OLLAMA_BASE_URL}/api/delete",
                json={"name": model_name},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Model deleted: {model_name}")
                    return web.json_response({"status": "deleted", "name": model_name})
                error = await resp.text()
                return web.json_response(
                    {"error": error}, status=resp.status
                )
        except Exception as e:
            return web.json_response({"error": str(e)}, status=502)

    app.router.add_post("/chat", handle_chat)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/models", handle_models_list)
    app.router.add_post("/models/pull", handle_models_pull)
    app.router.add_delete("/models", handle_models_delete)
    return app


async def _process_chat(brain, user_message: str) -> dict:
    """Process a single chat message through ReAct loop + cleanup + TTS."""
    # Build context from WorldModel
    world_context = brain.world_model.get_llm_context()
    system_msg = build_chat_system_message(world_context)

    # Build messages (no history — ephemeral)
    messages = [
        system_msg,
        {"role": "user", "content": user_message},
    ]

    # ReAct loop with read-only tools
    raw_content = ""
    for iteration in range(1, CHAT_MAX_ITERATIONS + 1):
        response = await brain.llm.chat(messages, CHAT_TOOLS)
        if response.error:
            logger.warning(f"Chat LLM error: {response.error}")
            return {"content": "うーん、LLMに接続できない", "audio_url": None}

        if not response.tool_calls:
            raw_content = response.content or ""
            break

        # Process tool calls
        assistant_msg = {"role": "assistant", "content": response.content or ""}
        assistant_msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": json.dumps(
                        tc["function"]["arguments"], ensure_ascii=False
                    ),
                },
            }
            for tc in response.tool_calls
        ]
        messages.append(assistant_msg)

        for tc in response.tool_calls:
            tool_name = tc["function"]["name"]
            arguments = tc["function"]["arguments"]
            result = await brain.tool_executor.execute(tool_name, arguments)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": str(result.get("result") or result.get("error", "")),
                }
            )
            logger.debug(
                f"Chat tool: {tool_name} → {'ok' if result.get('success') else 'err'}"
            )
    else:
        # Exhausted iterations — use last content
        raw_content = raw_content or "ちょっと複雑すぎて答えられなかった"

    # Cleanup with small LLM (if configured)
    content = await _cleanup_response(brain, raw_content)

    # Truncate to max chars
    if len(content) > CHAT_MAX_RESPONSE_CHARS:
        # Find last sentence boundary before limit
        truncated = content[:CHAT_MAX_RESPONSE_CHARS]
        for sep in ("。", "！", "？", "、", "！", "？"):
            idx = truncated.rfind(sep)
            if idx > 0:
                truncated = truncated[: idx + 1]
                break
        content = truncated

    # Classify tone and pick reaction motion
    tone = _classify_tone(content)
    motion_id = _pick_motion(tone, content)

    # Synthesize TTS with tone
    audio_url = await _synthesize_tts(brain, content, tone)

    return {"content": content, "audio_url": audio_url, "tone": tone, "motion_id": motion_id}


def _pick_motion(tone: str, content: str) -> str | None:
    """Select a reaction motion based on response tone and content keywords."""
    if any(w in content for w in ("了解", "わかった", "うん", "はい", "なるほど", "そうだね")):
        return "nod_agree"
    if any(w in content for w in ("？", "かな", "わからない", "難しい", "どうだろ")):
        return "head_tilt"
    if any(w in content for w in ("よろしく", "はじめ", "ありがとう", "どうぞ")):
        return "small_bow"
    if tone == "alert":
        return "head_tilt"
    return None


def _classify_tone(content: str) -> str:
    """Classify response tone by keywords (no LLM call needed)."""
    if any(w in content for w in ("すぐに", "危険", "注意", "やばい", "緊急", "警告", "たいへん", "あわわ")):
        return "alert"
    if any(w in content for w in ("ありがと", "大丈夫", "心配", "気をつけ", "てね", "だからね")):
        return "caring"
    if any(w in content for w in ("なんちゃって", "知らんけど", "えへへ", "うなうな", "笑")):
        return "humorous"
    return "neutral"


async def _cleanup_response(brain, raw: str) -> str:
    """Persona-rewrite: clean up and rewrite in character voice."""
    if not CLEANUP_MODEL or not raw:
        return raw

    if len(raw) <= CHAT_MAX_RESPONSE_CHARS:
        return raw

    try:
        cleanup_llm = LLMClient(api_url=LLM_API_URL, session=brain._session)
        cleanup_llm.model = CLEANUP_MODEL

        cleanup_messages = [
            {
                "role": "user",
                "content": build_cleanup_prompt(raw),
            }
        ]
        response = await cleanup_llm.chat(cleanup_messages)
        if response.content and not response.error:
            return response.content.strip()
    except Exception as e:
        logger.debug(f"Cleanup LLM failed (using raw): {e}")

    return raw


async def _synthesize_tts(brain, text: str, tone: str = "neutral") -> str | None:
    """Synthesize TTS audio via Voice Service."""
    if not text:
        return None
    try:
        async with brain._session.post(
            f"{VOICE_SERVICE_URL}/api/voice/synthesize",
            json={"text": text, "tone": tone},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("audio_url")
    except Exception as e:
        logger.debug(f"Chat TTS failed (non-fatal): {e}")
    return None
