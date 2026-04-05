"""VOICEPEAK TTS Provider — host bridge-based synthesis.

Calls the voicepeak_bridge HTTP server (runs on the host) because the voicepeak
CLI requires host audio/system resources unavailable in Docker.
"""

import os

import aiohttp
from loguru import logger

from tts_provider import TTSProvider, AudioResult

VOICEPEAK_BRIDGE_URL = os.getenv(
    "VOICEPEAK_BRIDGE_URL", "http://host.docker.internal:18100"
)
VOICEPEAK_NARRATOR = os.getenv("VOICEPEAK_NARRATOR", "Otomachi Una")


class VoicepeakProvider(TTSProvider):
    """VOICEPEAK speech synthesis via host bridge server."""

    def __init__(
        self,
        bridge_url: str | None = None,
        narrator: str | None = None,
    ):
        self.bridge_url = (bridge_url or VOICEPEAK_BRIDGE_URL).rstrip("/")
        self.narrator = narrator or VOICEPEAK_NARRATOR
        logger.info(
            f"VoicepeakProvider initialized: bridge={self.bridge_url}, "
            f"narrator={self.narrator}"
        )

    @property
    def name(self) -> str:
        return "voicepeak"

    async def synthesize(
        self, text: str, voice: str = "neutral", speed: float = 1.0
    ) -> AudioResult:
        payload = {"text": text, "narrator": self.narrator}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.bridge_url}/synthesize",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"Bridge returned {resp.status}: {body}")
                    wav_bytes = await resp.read()
            logger.info(
                f"VOICEPEAK synthesized {len(wav_bytes)} bytes for: {text[:40]!r}"
            )
            return AudioResult(
                audio_data=wav_bytes, format="wav", sample_rate=44100
            )
        except Exception as e:
            logger.error(f"VOICEPEAK bridge synthesis error: {e}")
            raise

    async def is_available(self) -> bool:
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                async with session.get(f"{self.bridge_url}/health") as resp:
                    data = await resp.json()
                    return data.get("status") == "ok"
        except Exception:
            return False

    async def get_speaker_name(self) -> str:
        return self.narrator
