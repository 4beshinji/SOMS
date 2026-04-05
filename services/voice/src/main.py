from contextlib import asynccontextmanager
import asyncio
import hmac
import os
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import uuid
from loguru import logger

INTERNAL_SERVICE_TOKEN: str | None = os.getenv("INTERNAL_SERVICE_TOKEN") or None


def _verify_service_token(token: str | None) -> None:
    """Verify internal service token for admin operations."""
    if INTERNAL_SERVICE_TOKEN is None:
        return  # No token configured — allow (dev mode)
    if not token or not hmac.compare_digest(token, INTERNAL_SERVICE_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid service token")

from models import TaskAnnounceRequest, SynthesizeRequest, VoiceResponse, DualVoiceResponse
from provider_factory import create_provider
from speech_generator import SpeechGenerator
from rejection_stock import RejectionStock, idle_generation_loop
from acceptance_stock import AcceptanceStock, idle_acceptance_generation_loop
from currency_unit_stock import CurrencyUnitStock, idle_currency_generation_loop

# Create TTS provider via factory
voice_provider = create_provider()

speech_gen = SpeechGenerator()

# Currency unit stock (text-only, injected into speech_gen)
currency_unit_stock = CurrencyUnitStock(speech_gen)
speech_gen.currency_stock = currency_unit_stock

# Rejection voice stock
rejection_stock = RejectionStock(speech_gen, voice_provider)

# Acceptance voice stock
acceptance_stock = AcceptanceStock(speech_gen, voice_provider)

# Audio storage directory
AUDIO_DIR = Path("/app/audio")
AUDIO_DIR.mkdir(exist_ok=True)


def estimate_audio_duration(audio_data: bytes) -> float:
    """Estimate audio duration in seconds by parsing the WAV header."""
    import struct
    try:
        if len(audio_data) >= 44 and audio_data[:4] == b"RIFF":
            sample_rate = struct.unpack_from("<I", audio_data, 24)[0]
            channels = struct.unpack_from("<H", audio_data, 22)[0]
            bits_per_sample = struct.unpack_from("<H", audio_data, 34)[0]
            pos = 12
            while pos < len(audio_data) - 8:
                chunk_id = audio_data[pos : pos + 4]
                chunk_size = struct.unpack_from("<I", audio_data, pos + 4)[0]
                if chunk_id == b"data":
                    bytes_per_sample = max(1, bits_per_sample // 8)
                    denom = sample_rate * channels * bytes_per_sample
                    return round(chunk_size / denom, 2)
                pos += 8 + chunk_size
                if chunk_size % 2:
                    pos += 1
    except Exception:
        pass
    # Fallback: assume VOICEVOX 24 kHz 16-bit mono
    return round(len(audio_data) / (24000 * 2), 2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start idle generation background tasks
    rejection_task = asyncio.create_task(idle_generation_loop(rejection_stock))
    acceptance_task = asyncio.create_task(idle_acceptance_generation_loop(acceptance_stock))
    currency_task = asyncio.create_task(idle_currency_generation_loop(currency_unit_stock))
    logger.info("Background idle generation tasks started (rejection + acceptance + currency)")
    yield
    rejection_task.cancel()
    acceptance_task.cancel()
    currency_task.cancel()
    for t in [rejection_task, acceptance_task, currency_task]:
        try:
            await t
        except asyncio.CancelledError:
            pass


# Initialize FastAPI app
app = FastAPI(
    title="SOMS Voice Service",
    description="Voice notification service using VOICEVOX and LLM",
    lifespan=lifespan,
)

@app.get("/")
async def root():
    """Basic health check endpoint."""
    return {"service": "SOMS Voice Service", "status": "running"}


@app.get("/health")
async def health():
    """Detailed health check: TTS backend + LLM connectivity."""
    import aiohttp
    from fastapi.responses import JSONResponse

    checks = {}

    # TTS backend check
    try:
        available = await voice_provider.is_available()
        checks[voice_provider.name] = "ok" if available else "unreachable"
    except Exception as e:
        checks[voice_provider.name] = f"error: {e}"

    # LLM check
    try:
        llm_url = speech_gen.llm_api_url.rstrip("/")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(f"{llm_url}/models") as resp:
                checks["llm"] = "ok" if resp.status == 200 else f"status={resp.status}"
    except Exception as e:
        checks["llm"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    return JSONResponse(
        content={"status": "healthy" if all_ok else "degraded", "checks": checks},
        status_code=status_code,
    )

@app.post("/api/voice/synthesize", response_model=VoiceResponse)
async def synthesize_text(request: SynthesizeRequest):
    """
    Synthesize text directly to speech (skips LLM text generation).
    Used by the speak tool where the Brain LLM has already generated the message.
    """
    rejection_stock.request_started()
    acceptance_stock.request_started()
    currency_unit_stock.request_started()
    try:
        logger.info(f"Synthesizing text: {request.text[:50]}...")

        result = await voice_provider.synthesize(request.text)

        audio_id = str(uuid.uuid4())
        audio_filename = f"speak_{audio_id}.mp3"
        audio_path = AUDIO_DIR / audio_filename
        await voice_provider.save_audio(result.audio_data, audio_path)

        duration_seconds = result.duration or estimate_audio_duration(result.audio_data)

        return VoiceResponse(
            audio_url=f"/audio/{audio_filename}",
            text_generated=request.text,
            duration_seconds=duration_seconds
        )

    except Exception as e:
        logger.error(f"Failed to synthesize text: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rejection_stock.request_finished()
        acceptance_stock.request_finished()
        currency_unit_stock.request_finished()

@app.post("/api/voice/announce", response_model=VoiceResponse)
async def announce_task(request: TaskAnnounceRequest):
    """
    Generate voice announcement for a task.

    Flow:
    1. Generate natural speech text using LLM
    2. Synthesize using TTS provider
    3. Save audio file
    4. Return audio URL and metadata
    """
    rejection_stock.request_started()
    acceptance_stock.request_started()
    currency_unit_stock.request_started()
    try:
        logger.info(f"Announcing task: {request.task.title}")

        speech_text = await speech_gen.generate_speech_text(request.task)
        result = await voice_provider.synthesize(speech_text)

        audio_id = str(uuid.uuid4())
        audio_filename = f"task_{audio_id}.mp3"
        audio_path = AUDIO_DIR / audio_filename
        await voice_provider.save_audio(result.audio_data, audio_path)

        duration_seconds = result.duration or estimate_audio_duration(result.audio_data)

        return VoiceResponse(
            audio_url=f"/audio/{audio_filename}",
            text_generated=speech_text,
            duration_seconds=duration_seconds
        )

    except Exception as e:
        logger.error(f"Failed to announce task: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rejection_stock.request_finished()
        acceptance_stock.request_finished()
        currency_unit_stock.request_finished()

@app.post("/api/voice/feedback/{feedback_type}")
async def generate_feedback(feedback_type: str):
    """
    Generate feedback message (e.g., task completion acknowledgment).

    Args:
        feedback_type: Type of feedback ('task_completed', 'task_accepted')
    """
    rejection_stock.request_started()
    acceptance_stock.request_started()
    currency_unit_stock.request_started()
    try:
        logger.info(f"Generating feedback: {feedback_type}")

        feedback_text = await speech_gen.generate_feedback(feedback_type)
        result = await voice_provider.synthesize(feedback_text)

        audio_id = str(uuid.uuid4())
        audio_filename = f"feedback_{audio_id}.mp3"
        audio_path = AUDIO_DIR / audio_filename
        await voice_provider.save_audio(result.audio_data, audio_path)

        duration_seconds = result.duration or estimate_audio_duration(result.audio_data)

        return VoiceResponse(
            audio_url=f"/audio/{audio_filename}",
            text_generated=feedback_text,
            duration_seconds=duration_seconds
        )

    except Exception as e:
        logger.error(f"Failed to generate feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rejection_stock.request_finished()
        acceptance_stock.request_finished()
        currency_unit_stock.request_finished()

@app.post("/api/voice/announce_with_completion", response_model=DualVoiceResponse)
async def announce_task_with_completion(request: TaskAnnounceRequest):
    """
    Generate both announcement and completion voices for a task.
    The completion voice is contextually linked to the task content.
    """
    rejection_stock.request_started()
    acceptance_stock.request_started()
    currency_unit_stock.request_started()
    try:
        logger.info(f"Generating dual voice for task: {request.task.title}")

        announcement_text = await speech_gen.generate_speech_text(request.task)
        completion_text = await speech_gen.generate_completion_text(request.task)

        announcement_result = await voice_provider.synthesize(announcement_text)
        completion_result = await voice_provider.synthesize(
            completion_text, voice="completion"
        )

        announcement_id = str(uuid.uuid4())
        announcement_filename = f"task_announce_{announcement_id}.mp3"
        announcement_path = AUDIO_DIR / announcement_filename
        await voice_provider.save_audio(announcement_result.audio_data, announcement_path)

        completion_id = str(uuid.uuid4())
        completion_filename = f"task_complete_{completion_id}.mp3"
        completion_path = AUDIO_DIR / completion_filename
        await voice_provider.save_audio(completion_result.audio_data, completion_path)

        announcement_duration = (
            announcement_result.duration
            or estimate_audio_duration(announcement_result.audio_data)
        )
        completion_duration = (
            completion_result.duration
            or estimate_audio_duration(completion_result.audio_data)
        )

        logger.info(f"Announcement: {announcement_text}")
        logger.info(f"Completion: {completion_text}")

        return DualVoiceResponse(
            announcement_audio_url=f"/audio/{announcement_filename}",
            announcement_text=announcement_text,
            announcement_duration=announcement_duration,
            completion_audio_url=f"/audio/{completion_filename}",
            completion_text=completion_text,
            completion_duration=completion_duration
        )

    except Exception as e:
        logger.error(f"Failed to generate dual voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rejection_stock.request_finished()
        acceptance_stock.request_finished()
        currency_unit_stock.request_finished()

@app.get("/api/voice/credit")
async def get_voice_credit():
    """Return voice character credit info for license compliance."""
    name = await voice_provider.get_speaker_name()
    return {"engine": voice_provider.name.upper(), "character": name}


@app.get("/api/voice/rejection/random")
async def get_random_rejection():
    """
    Get a random pre-generated rejection voice from stock.
    Returns instantly (no synthesis latency) if stock is available.
    Falls back to on-demand synthesis if stock is empty.
    """
    entry = await rejection_stock.get_random()
    if entry:
        return entry

    # Fallback: generate on-demand (slower, but avoids silence)
    logger.warning("Rejection stock empty, generating on-demand")
    rejection_stock.request_started()
    acceptance_stock.request_started()
    currency_unit_stock.request_started()
    try:
        text = await speech_gen.generate_rejection_text()
        result = await voice_provider.synthesize(text, voice="rejection")
        audio_id = str(uuid.uuid4())[:8]
        audio_filename = f"rejection_ondemand_{audio_id}.mp3"
        audio_path = AUDIO_DIR / audio_filename
        await voice_provider.save_audio(result.audio_data, audio_path)
        return {"audio_url": f"/audio/{audio_filename}", "text": text}
    except Exception as e:
        logger.error(f"On-demand rejection generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rejection_stock.request_finished()
        acceptance_stock.request_finished()
        currency_unit_stock.request_finished()


@app.get("/api/voice/rejection/status")
async def get_rejection_status():
    """Get current rejection voice stock status."""
    return {
        "stock_count": rejection_stock.count,
        "max_stock": 100,
        "is_generating": not rejection_stock.is_idle,
        "needs_refill": rejection_stock.needs_refill,
    }


@app.post("/api/voice/rejection/clear")
async def clear_rejection_stock(x_service_token: str = Header(None, alias="X-Service-Token")):
    """Clear all pre-generated rejection stock and force regeneration."""
    _verify_service_token(x_service_token)
    await rejection_stock.clear_all()
    return {"status": "cleared", "stock_count": rejection_stock.count}


@app.get("/api/voice/acceptance/random")
async def get_random_acceptance():
    """
    Get a random pre-generated acceptance voice from stock.
    Returns instantly (no synthesis latency) if stock is available.
    Falls back to on-demand synthesis if stock is empty.
    """
    entry = await acceptance_stock.get_random()
    if entry:
        return entry

    # Fallback: generate on-demand (slower, but avoids silence)
    logger.warning("Acceptance stock empty, generating on-demand")
    rejection_stock.request_started()
    acceptance_stock.request_started()
    currency_unit_stock.request_started()
    try:
        text = await speech_gen.generate_acceptance_text()
        result = await voice_provider.synthesize(text, voice="acceptance")
        audio_id = str(uuid.uuid4())[:8]
        audio_filename = f"acceptance_ondemand_{audio_id}.mp3"
        audio_path = AUDIO_DIR / audio_filename
        await voice_provider.save_audio(result.audio_data, audio_path)
        return {"audio_url": f"/audio/{audio_filename}", "text": text}
    except Exception as e:
        logger.error(f"On-demand acceptance generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        rejection_stock.request_finished()
        acceptance_stock.request_finished()
        currency_unit_stock.request_finished()


@app.get("/api/voice/acceptance/status")
async def get_acceptance_status():
    """Get current acceptance voice stock status."""
    return {
        "stock_count": acceptance_stock.count,
        "max_stock": 50,
        "is_generating": not acceptance_stock.is_idle,
        "needs_refill": acceptance_stock.needs_refill,
    }


@app.post("/api/voice/acceptance/clear")
async def clear_acceptance_stock(x_service_token: str = Header(None, alias="X-Service-Token")):
    """Clear all pre-generated acceptance stock and force regeneration."""
    _verify_service_token(x_service_token)
    await acceptance_stock.clear_all()
    return {"status": "cleared", "stock_count": acceptance_stock.count}


@app.get("/api/voice/currency-units/status")
async def get_currency_unit_status():
    """Get current currency unit stock status."""
    return {
        "stock_count": currency_unit_stock.count,
        "max_stock": 50,
        "needs_refill": currency_unit_stock.needs_refill,
        "sample": currency_unit_stock.get_random(),
    }


@app.post("/api/voice/currency-units/clear")
async def clear_currency_unit_stock(x_service_token: str = Header(None, alias="X-Service-Token")):
    """Clear all pre-generated currency unit stock and force regeneration."""
    _verify_service_token(x_service_token)
    await currency_unit_stock.clear_all()
    return {"status": "cleared", "stock_count": currency_unit_stock.count}


def _safe_audio_path(base_dir: Path, filename: str) -> Path:
    """Resolve path and verify it stays within base directory."""
    resolved = (base_dir / filename).resolve()
    if not resolved.is_relative_to(base_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return resolved


@app.get("/audio/rejections/{filename}")
async def serve_rejection_audio(filename: str):
    """Serve pre-generated rejection audio files."""
    from rejection_stock import STOCK_DIR
    audio_path = _safe_audio_path(STOCK_DIR, filename)

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")

    return FileResponse(audio_path, media_type="audio/mpeg")


@app.get("/audio/acceptances/{filename}")
async def serve_acceptance_audio(filename: str):
    """Serve pre-generated acceptance audio files."""
    from acceptance_stock import STOCK_DIR
    audio_path = _safe_audio_path(STOCK_DIR, filename)

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")

    return FileResponse(audio_path, media_type="audio/mpeg")


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve generated audio files."""
    audio_path = _safe_audio_path(AUDIO_DIR, filename)

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")

    return FileResponse(
        audio_path,
        media_type="audio/mpeg"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
