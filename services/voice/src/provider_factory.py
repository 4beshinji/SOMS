"""TTS provider factory — creates the appropriate provider based on config."""

import os

from loguru import logger

from tts_provider import TTSProvider


def create_provider() -> TTSProvider:
    """Create TTS provider from environment configuration."""
    backend = os.getenv("TTS_BACKEND", "voicepeak").lower()

    logger.info(f"Creating TTS provider: {backend}")

    if backend == "voicepeak":
        from providers.voicepeak import VoicepeakProvider

        return VoicepeakProvider()
    elif backend == "voicevox":
        from providers.voicevox import VoicevoxProvider

        return VoicevoxProvider()
    else:
        logger.warning(f"Unknown TTS backend '{backend}', falling back to voicevox")
        from providers.voicevox import VoicevoxProvider

        return VoicevoxProvider()
