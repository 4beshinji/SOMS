"""
Minimal OpenAI-compatible STT server using transformers + PyTorch.
GPU-accelerated via ROCm on AMD GPUs.

Endpoints:
  POST /v1/audio/transcriptions  — OpenAI-compatible transcription
  GET  /health                   — Health check
"""

import io
import os
import tempfile
import time

import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

MODEL_ID = os.getenv("STT_MODEL", "kotoba-tech/kotoba-whisper-v2.0")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"  # ROCm exposes as cuda

app = FastAPI(title="SOMS STT Service")

# Lazy-loaded pipeline
_pipe = None


def _get_pipeline():
    global _pipe
    if _pipe is not None:
        return _pipe

    from transformers import pipeline

    torch_dtype = torch.float16 if DEVICE == "cuda" else torch.float32
    _pipe = pipeline(
        "automatic-speech-recognition",
        model=MODEL_ID,
        torch_dtype=torch_dtype,
        device=DEVICE,
        model_kwargs={"attn_implementation": "sdpa"},
    )
    return _pipe


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form("ja"),
    response_format: str = Form("json"),
):
    """OpenAI-compatible transcription endpoint."""
    start = time.monotonic()

    # Read uploaded audio
    audio_bytes = await file.read()

    # Decode audio to numpy array
    try:
        audio_data, sample_rate = sf.read(io.BytesIO(audio_bytes))
    except Exception:
        # Fallback: write to temp file for ffmpeg-based formats
        with tempfile.NamedTemporaryFile(suffix=_guess_ext(file.filename), delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            audio_data, sample_rate = sf.read(tmp_path)
        finally:
            os.unlink(tmp_path)

    # Convert stereo to mono
    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)

    # Resample to 16kHz if needed
    if sample_rate != 16000:
        import numpy as np
        ratio = 16000 / sample_rate
        new_len = int(len(audio_data) * ratio)
        indices = np.linspace(0, len(audio_data) - 1, new_len)
        audio_data = np.interp(indices, np.arange(len(audio_data)), audio_data)

    # Run inference
    pipe = _get_pipeline()
    generate_kwargs = {"language": language, "task": "transcribe"}
    result = pipe(
        audio_data.astype("float32"),
        chunk_length_s=30,
        batch_size=8,
        generate_kwargs=generate_kwargs,
    )

    elapsed = time.monotonic() - start
    text = result["text"].strip()

    if response_format == "verbose_json":
        return JSONResponse({
            "text": text,
            "language": language,
            "duration": float(len(audio_data) / 16000),
            "processing_time": round(elapsed, 3),
        })

    return JSONResponse({"text": text})


@app.get("/health")
async def health():
    device_info = f"ROCm ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else "CPU"
    loaded = _pipe is not None
    return {
        "status": "ok",
        "device": device_info,
        "model": MODEL_ID,
        "model_loaded": loaded,
    }


def _guess_ext(filename: str | None) -> str:
    if not filename:
        return ".wav"
    for ext in (".webm", ".ogg", ".mp3", ".mp4", ".m4a", ".flac"):
        if filename.endswith(ext):
            return ext
    return ".wav"


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
