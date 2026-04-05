"""VOICEVOX TTS Provider — Docker-based Japanese speech synthesis."""

import os
import random

import aiohttp
from loguru import logger

from tts_provider import TTSProvider, AudioResult

VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://voicevox:50021")

# ナースロボ＿タイプＴ style variants
SPEAKER_NORMAL = 47   # ノーマル
SPEAKER_HAPPY = 48    # 楽しい
SPEAKER_COOL = 46     # クール
SPEAKER_WHISPER = 49  # ささやき

# Voice name → speaker ID pool mapping
VOICE_SPEAKERS: dict[str, list[int]] = {
    "neutral":    [SPEAKER_NORMAL],
    "caring":     [SPEAKER_NORMAL],
    "humorous":   [SPEAKER_HAPPY],
    "alert":      [SPEAKER_COOL],
    "happy":      [SPEAKER_HAPPY],
    "rejection":  [SPEAKER_NORMAL, SPEAKER_COOL],
    "completion": [SPEAKER_NORMAL, SPEAKER_HAPPY],
    "acceptance": [SPEAKER_NORMAL, SPEAKER_HAPPY],
}


class VoicevoxProvider(TTSProvider):
    """VOICEVOX speech synthesis provider."""

    _speaker_name_cache: dict[int, str] | None = None

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or VOICEVOX_URL
        logger.info(f"VoicevoxProvider initialized: {self.base_url}")

    @property
    def name(self) -> str:
        return "voicevox"

    def _resolve_speaker(self, voice: str) -> int:
        pool = VOICE_SPEAKERS.get(voice, VOICE_SPEAKERS["neutral"])
        return random.choice(pool)

    async def synthesize(
        self, text: str, voice: str = "neutral", speed: float = 1.0
    ) -> AudioResult:
        speaker_id = self._resolve_speaker(voice)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            # Step 1: Generate audio query
            async with session.post(
                f"{self.base_url}/audio_query",
                params={"text": text, "speaker": speaker_id},
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"VOICEVOX audio_query failed: {error_text}")
                query = await resp.json()

            if speed != 1.0:
                query["speedScale"] = speed

            # Step 2: Synthesize audio
            async with session.post(
                f"{self.base_url}/synthesis",
                params={"speaker": speaker_id},
                json=query,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"VOICEVOX synthesis failed: {error_text}")
                audio_data = await resp.read()

        logger.info(f"Synthesized {len(audio_data)} bytes (speaker={speaker_id})")
        return AudioResult(audio_data=audio_data, format="wav", sample_rate=24000)

    async def is_available(self) -> bool:
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                async with session.get(f"{self.base_url}/speakers") as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def get_speaker_name(self) -> str:
        if self._speaker_name_cache and SPEAKER_NORMAL in self._speaker_name_cache:
            return self._speaker_name_cache[SPEAKER_NORMAL]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/speakers") as resp:
                    if resp.status != 200:
                        return "VOICEVOX"
                    speakers = await resp.json()

            cache: dict[int, str] = {}
            for speaker in speakers:
                name = speaker.get("name", "")
                for style in speaker.get("styles", []):
                    cache[style["id"]] = name
            VoicevoxProvider._speaker_name_cache = cache
            return cache.get(SPEAKER_NORMAL, "VOICEVOX")
        except Exception as e:
            logger.warning(f"Failed to resolve speaker name: {e}")
            return "VOICEVOX"
