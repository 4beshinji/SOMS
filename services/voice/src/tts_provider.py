"""TTS Provider abstract base class.

All TTS backends (VOICEVOX, VOICEPEAK, etc.) implement this interface.
Pattern adapted from hems/voisona-yomiage.
"""

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from pydub import AudioSegment


@dataclass
class AudioResult:
    """TTS synthesis result."""

    audio_data: bytes
    format: str = "wav"
    sample_rate: int | None = None
    duration: float | None = None


class TTSProvider(ABC):
    """Abstract TTS provider interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        ...

    @abstractmethod
    async def synthesize(
        self, text: str, voice: str = "neutral", speed: float = 1.0
    ) -> AudioResult:
        """Synthesize text to audio.

        Args:
            text: Text to synthesize.
            voice: Tone/voice name (e.g. "neutral", "rejection", "acceptance").
            speed: Speed multiplier.

        Returns:
            AudioResult with WAV audio data.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the TTS backend is reachable."""
        ...

    async def get_speaker_name(self) -> str:
        """Return the character/speaker name for credit display."""
        return self.name

    async def save_audio(self, audio_data: bytes, filepath: Path) -> None:
        """Convert WAV bytes to MP3 and save."""
        try:
            wav_io = io.BytesIO(audio_data)
            audio_segment = AudioSegment.from_wav(wav_io)
            audio_segment.export(filepath, format="mp3", bitrate="64k")
            logger.info(f"Saved MP3: {filepath} ({filepath.stat().st_size} bytes)")
        except Exception as e:
            logger.error(f"Failed to save audio: {e}")
            raise
