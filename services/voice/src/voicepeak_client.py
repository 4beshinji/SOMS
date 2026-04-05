"""VoicepeakClient — drop-in replacement for VoicevoxClient.

Calls the voicepeak_bridge HTTP server (runs on the host) to perform synthesis,
because the voicepeak CLI requires host audio/system resources unavailable in Docker.

Set VOICEPEAK_BRIDGE_URL env var (default: http://host.docker.internal:18100).
"""

import io
from pathlib import Path

import aiohttp
from loguru import logger
from pydub import AudioSegment


class VoicepeakClient:
    """Client for VOICEPEAK speech synthesis via the host bridge server.

    API is intentionally compatible with VoicevoxClient so it can be used
    as a drop-in replacement without changing callers.
    """

    SAMPLE_RATE = 44100

    def __init__(
        self,
        bridge_url: str = "http://host.docker.internal:18100",
        narrator: str = "Otomachi Una",
    ):
        self.bridge_url = bridge_url.rstrip("/")
        self.narrator = narrator
        logger.info(
            f"VoicepeakClient initialized: bridge={bridge_url}, narrator={narrator}"
        )

    # ------------------------------------------------------------------
    # VoicevoxClient-compatible class-level helpers
    # ------------------------------------------------------------------

    @classmethod
    def pick_speaker(cls, context: str = "announcement") -> int:
        """Compatibility shim — voicepeak uses narrator names, not integer IDs."""
        return 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_speaker_name(self, speaker_id: int | None = None) -> str:
        return self.narrator

    async def synthesize(self, text: str, speaker_id: int | None = None) -> bytes:
        """Synthesize text via the voicepeak bridge and return raw WAV bytes.

        speaker_id is accepted for API compatibility but ignored.
        """
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
                        raise RuntimeError(
                            f"Bridge returned {resp.status}: {body}"
                        )
                    wav_bytes = await resp.read()
            logger.info(
                f"VOICEPEAK bridge synthesized {len(wav_bytes)} bytes for: {text[:40]!r}"
            )
            return wav_bytes
        except Exception as e:
            logger.error(f"VOICEPEAK bridge synthesis error: {e}")
            raise

    async def save_audio(self, audio_data: bytes, filepath: Path) -> None:
        """Convert WAV bytes to MP3 and save."""
        try:
            wav_io = io.BytesIO(audio_data)
            audio_segment = AudioSegment.from_wav(wav_io)
            audio_segment.export(filepath, format="mp3", bitrate="64k")
            logger.info(
                f"Saved MP3: {filepath} ({filepath.stat().st_size} bytes)"
            )
        except Exception as e:
            logger.error(f"Failed to save audio: {e}")
            raise


# ------------------------------------------------------------------
# WAV utilities (adapted from voisona-yomiage)
# ------------------------------------------------------------------

def _split_text(text: str, max_chars: int) -> list[str]:
    """Split text at sentence boundaries to stay within max_chars."""
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
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


def _find_data_offset(wav: bytes) -> int:
    pos = 12
    while pos < len(wav) - 8:
        chunk_id = wav[pos : pos + 4]
        chunk_size = struct.unpack_from("<I", wav, pos + 4)[0]
        if chunk_id == b"data":
            return pos + 8
        pos += 8 + chunk_size
        if chunk_size % 2:
            pos += 1
    raise ValueError("No data chunk in WAV")


def _concat_wav(wav_parts: list[bytes]) -> bytes:
    """Concatenate multiple 16-bit PCM WAV files."""
    if not wav_parts:
        return b""
    if len(wav_parts) == 1:
        return wav_parts[0]

    first = wav_parts[0]
    if len(first) < 44 or first[:4] != b"RIFF":
        raise ValueError("Invalid WAV data")

    fmt = first[12:]
    channels, sample_rate, bits_per_sample = 1, 44100, 16
    pos = 0
    while pos < len(fmt) - 8:
        cid = fmt[pos : pos + 4]
        csz = struct.unpack_from("<I", fmt, pos + 4)[0]
        if cid == b"fmt ":
            channels = struct.unpack_from("<H", fmt, pos + 10)[0]
            sample_rate = struct.unpack_from("<I", fmt, pos + 12)[0]
            bits_per_sample = struct.unpack_from("<H", fmt, pos + 22)[0]
        elif cid == b"data":
            break
        pos += 8 + csz
        if csz % 2:
            pos += 1

    pcm_parts = []
    for wav in wav_parts:
        offset = _find_data_offset(wav)
        data_size = struct.unpack_from("<I", wav, offset - 4)[0]
        pcm_parts.append(wav[offset : offset + data_size])

    total_pcm = b"".join(pcm_parts)
    total_size = len(total_pcm)
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8

    out = bytearray()
    out += b"RIFF"
    out += struct.pack("<I", 36 + total_size)
    out += b"WAVE"
    out += b"fmt "
    out += struct.pack("<I", 16)
    out += struct.pack("<H", 1)  # PCM
    out += struct.pack("<H", channels)
    out += struct.pack("<I", sample_rate)
    out += struct.pack("<I", byte_rate)
    out += struct.pack("<H", block_align)
    out += struct.pack("<H", bits_per_sample)
    out += b"data"
    out += struct.pack("<I", total_size)
    out += total_pcm
    return bytes(out)
