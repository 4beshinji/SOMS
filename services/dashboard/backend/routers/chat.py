"""
Chat router — ephemeral Q&A proxy to Brain chat server.
No conversation history; each request is independent.
Logs messages for analytics (auto-cleaned after 7 days).
"""
import os
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone

from database import get_db
import models
import schemas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

BRAIN_CHAT_URL = os.getenv("BRAIN_CHAT_URL", "http://brain:8080")
_BRAIN_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_MAX_LOGS = 500  # max log entries before auto-cleanup


@router.post("/", response_model=schemas.ChatResponse)
async def send_message(req: schemas.ChatRequest, db: AsyncSession = Depends(get_db)):
    """Send a chat message, get AI response via Brain."""
    message = req.message.strip()
    if not message:
        raise HTTPException(400, "Empty message")
    if len(message) > 500:
        raise HTTPException(400, "Message too long (max 500 chars)")

    # Proxy to Brain chat server
    brain_response = await _call_brain(message)

    content = brain_response.get("content", "")
    audio_url = brain_response.get("audio_url")
    tone = brain_response.get("tone")
    motion_id = brain_response.get("motion_id")
    raw_chunks = brain_response.get("chunks")

    # Build typed chunks if present
    chunks = None
    if raw_chunks:
        chunks = [
            schemas.ChatChunk(
                text=c.get("text", ""),
                audio_url=c.get("audio_url"),
                tone=c.get("tone"),
                motion_id=c.get("motion_id"),
            )
            for c in raw_chunks
        ]

    # Log for analytics
    log_entry = models.ChatLog(
        user_message=message[:500],
        assistant_message=content[:500],
        audio_url=audio_url,
    )
    db.add(log_entry)
    await db.commit()

    return schemas.ChatResponse(
        content=content, audio_url=audio_url, tone=tone,
        motion_id=motion_id, chunks=chunks,
    )


_BRAIN_STREAM_TIMEOUT = httpx.Timeout(120.0, connect=5.0)


@router.post("/stream")
async def send_message_stream(req: schemas.ChatRequest, db: AsyncSession = Depends(get_db)):
    """SSE streaming chat — proxy Brain /chat/stream to frontend."""
    from fastapi.responses import StreamingResponse

    message = req.message.strip()
    if not message:
        raise HTTPException(400, "Empty message")
    if len(message) > 500:
        raise HTTPException(400, "Message too long (max 500 chars)")

    async def proxy_sse():
        full_text_parts = []
        first_audio_url = None
        try:
            async with httpx.AsyncClient(timeout=_BRAIN_STREAM_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    f"{BRAIN_CHAT_URL}/chat/stream",
                    json={"user_message": message},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("event: "):
                            yield line + "\n"
                        elif line.startswith("data: "):
                            yield line + "\n\n"
                            # Parse for logging
                            try:
                                import json
                                data = json.loads(line[6:])
                                if "text" in data:
                                    full_text_parts.append(data["text"])
                                    if first_audio_url is None:
                                        first_audio_url = data.get("audio_url")
                            except Exception:
                                pass
        except Exception as e:
            logger.warning("Brain SSE proxy error: %s", e)
            yield f"event: error\ndata: {{\"message\": \"stream failed\"}}\n\n"

        # Log for analytics (fire-and-forget after stream ends)
        try:
            full_text = "".join(full_text_parts)
            log_entry = models.ChatLog(
                user_message=message[:500],
                assistant_message=full_text[:500],
                audio_url=first_audio_url,
            )
            db.add(log_entry)
            await db.commit()
        except Exception:
            pass

    return StreamingResponse(
        proxy_sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history", response_model=list[schemas.ChatLogResponse])
async def get_history(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Get recent chat logs."""
    limit = min(limit, 100)
    result = await db.execute(
        select(models.ChatLog)
        .order_by(models.ChatLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [schemas.ChatLogResponse.model_validate(log) for log in reversed(logs)]


@router.delete("/cleanup")
async def cleanup_old_logs(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
):
    """Delete chat logs older than N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        delete(models.ChatLog).where(models.ChatLog.created_at < cutoff)
    )
    await db.commit()
    return {"deleted": result.rowcount}


@router.get("/models")
async def list_models():
    """List available Ollama models via Brain proxy."""
    try:
        async with httpx.AsyncClient(timeout=_BRAIN_TIMEOUT) as client:
            resp = await client.get(f"{BRAIN_CHAT_URL}/models")
            return resp.json()
    except Exception as e:
        raise HTTPException(502, f"Failed to list models: {e}")


@router.post("/models/pull")
async def pull_model(req: dict):
    """Pull an Ollama model. Returns streaming NDJSON progress."""
    from fastapi.responses import StreamingResponse

    model_name = req.get("name", "").strip()
    if not model_name:
        raise HTTPException(400, "Missing 'name'")

    async def stream():
        async with httpx.AsyncClient(timeout=httpx.Timeout(3600.0, connect=10.0)) as client:
            async with client.stream(
                "POST",
                f"{BRAIN_CHAT_URL}/models/pull",
                json={"name": model_name},
            ) as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.delete("/models")
async def delete_model(req: dict):
    """Delete an Ollama model via Brain proxy."""
    try:
        async with httpx.AsyncClient(timeout=_BRAIN_TIMEOUT) as client:
            resp = await client.request(
                "DELETE", f"{BRAIN_CHAT_URL}/models", json=req
            )
            return resp.json()
    except Exception as e:
        raise HTTPException(502, f"Failed to delete model: {e}")


async def _call_brain(user_message: str) -> dict:
    """Proxy chat request to Brain HTTP server."""
    try:
        async with httpx.AsyncClient(timeout=_BRAIN_TIMEOUT) as client:
            resp = await client.post(
                f"{BRAIN_CHAT_URL}/chat",
                json={"user_message": user_message},
            )
            if resp.status_code != 200:
                logger.warning("Brain chat error: %d %s", resp.status_code, resp.text[:200])
                raise HTTPException(502, "Brain chat request failed")
            return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "Brain chat timeout")
    except httpx.ConnectError:
        logger.warning("Brain chat server unreachable at %s", BRAIN_CHAT_URL)
        raise HTTPException(502, "Brain chat server unreachable")
