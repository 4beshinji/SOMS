"""
Voicepeak synthesis bridge server.

Runs on the HOST (not in Docker) so that the voicepeak CLI has full access
to audio drivers and system resources it needs.

Usage:
    python3 services/voice/voicepeak_bridge.py

Then set VOICEPEAK_BRIDGE_URL=http://host.docker.internal:18100 in .env
so the Docker voice-service uses this bridge instead of calling voicepeak directly.
"""

import asyncio
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

VOICEPEAK_PATH = os.getenv(
    "VOICEPEAK_PATH",
    "/home/sin/code/una/Voicepeak-linux64/Voicepeak/voicepeak",
)
DEFAULT_NARRATOR = os.getenv("VOICEPEAK_NARRATOR", "Otomachi Una")
PORT = int(os.getenv("VOICEPEAK_BRIDGE_PORT", "18100"))
MAX_CHARS = 140

app = FastAPI(title="Voicepeak Bridge")


class SynthRequest(BaseModel):
    text: str
    narrator: str = DEFAULT_NARRATOR
    speed: int = 100
    pitch: int = 0


@app.get("/health")
async def health():
    try:
        result = subprocess.run(
            [VOICEPEAK_PATH, "--list-narrator"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {"status": "error", "detail": "voicepeak not available"}
        narrators = [l.strip() for l in result.stdout.decode().splitlines() if l.strip()]
        return {"status": "ok", "narrators": narrators}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/synthesize")
async def synthesize(req: SynthRequest):
    """Synthesize text and return WAV bytes."""
    chunks = _split_text(req.text, MAX_CHARS)
    wav_parts = []

    with tempfile.TemporaryDirectory(prefix="vpbridge_") as tmpdir:
        for i, chunk in enumerate(chunks):
            outfile = Path(tmpdir) / f"chunk_{i:04d}.wav"
            cmd = [VOICEPEAK_PATH, "-s", chunk, "-o", str(outfile)]
            if req.narrator:
                cmd += ["-n", req.narrator]
            if req.speed != 100:
                cmd += ["--speed", str(req.speed)]
            if req.pitch != 0:
                cmd += ["--pitch", str(req.pitch)]

            result = subprocess.run(cmd, capture_output=True, timeout=60)
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace").strip()
                raise HTTPException(
                    status_code=500,
                    detail=f"voicepeak failed (rc={result.returncode}): {stderr}",
                )
            if not outfile.exists():
                raise HTTPException(
                    status_code=500,
                    detail="voicepeak produced no output",
                )
            wav_parts.append(outfile.read_bytes())

    if len(wav_parts) == 1:
        wav_data = wav_parts[0]
    else:
        wav_data = _concat_wav(wav_parts)

    return Response(content=wav_data, media_type="audio/wav")


def _split_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        best = -1
        for marker in ("。", "！", "？", "!", "?"):
            pos = remaining.rfind(marker, 0, max_chars)
            if pos > best:
                best = pos
        if best > 0:
            chunks.append(remaining[: best + 1])
            remaining = remaining[best + 1 :]
        else:
            chunks.append(remaining[:max_chars])
            remaining = remaining[max_chars:]
    return [c for c in chunks if c.strip()]


def _concat_wav(wav_parts: list[bytes]) -> bytes:
    import struct

    def find_data(wav: bytes) -> tuple[int, int]:
        pos = 12
        while pos < len(wav) - 8:
            cid = wav[pos : pos + 4]
            csz = struct.unpack_from("<I", wav, pos + 4)[0]
            if cid == b"data":
                return pos + 8, csz
            pos += 8 + csz
            if csz % 2:
                pos += 1
        raise ValueError("No data chunk")

    first = wav_parts[0]
    channels = struct.unpack_from("<H", first, 22)[0]
    sample_rate = struct.unpack_from("<I", first, 24)[0]
    bits_per_sample = struct.unpack_from("<H", first, 34)[0]

    pcm = b"".join(
        wav[off : off + sz] for wav in wav_parts for off, sz in [find_data(wav)]
    )
    total = len(pcm)
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8

    out = bytearray()
    out += b"RIFF" + struct.pack("<I", 36 + total) + b"WAVE"
    out += b"fmt " + struct.pack("<I", 16)
    out += struct.pack("<H", 1)  # PCM
    out += struct.pack("<H", channels)
    out += struct.pack("<I", sample_rate)
    out += struct.pack("<I", byte_rate)
    out += struct.pack("<H", block_align)
    out += struct.pack("<H", bits_per_sample)
    out += b"data" + struct.pack("<I", total) + pcm
    return bytes(out)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
