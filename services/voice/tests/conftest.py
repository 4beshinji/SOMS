"""Shared fixtures and helpers for voice service unit tests."""
import sys
import os
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_THIS_DIR = str(Path(__file__).resolve().parent)
VOICE_SRC = str(Path(__file__).resolve().parent.parent / "src")

# Add voice/src to sys.path so test-file imports resolve correctly
if VOICE_SRC not in sys.path:
    sys.path.insert(0, VOICE_SRC)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# Set test-safe environment BEFORE importing any voice modules
os.environ.setdefault("LLM_API_URL", "http://test-llm:8000/v1")
os.environ.setdefault("LLM_MODEL", "test-model")

# ── Mock missing optional dependencies ───────────────────────────
# pydub is used by voicevox_client.py but is not installed in the test venv.
# We inject a stub module so imports succeed without the real library.
if "pydub" not in sys.modules:
    _pydub = types.ModuleType("pydub")
    _pydub.AudioSegment = MagicMock()
    sys.modules["pydub"] = _pydub

# ── Redirect module-level Path constants ─────────────────────────
# main.py (and the stock modules it imports) execute code at import time
# that creates directories under /app/audio. We redirect these paths to
# a temp directory BEFORE any test imports main.py.
_TEST_TMPDIR = Path(tempfile.mkdtemp(prefix="soms_voice_test_"))
_TEST_AUDIO_DIR = _TEST_TMPDIR / "audio"
_TEST_AUDIO_DIR.mkdir(exist_ok=True)
_TEST_REJECTIONS_DIR = _TEST_AUDIO_DIR / "rejections"
_TEST_REJECTIONS_DIR.mkdir(exist_ok=True)
_TEST_ACCEPTANCES_DIR = _TEST_AUDIO_DIR / "acceptances"
_TEST_ACCEPTANCES_DIR.mkdir(exist_ok=True)

# Patch stock module constants before any import of main
import rejection_stock as _rs_mod
import acceptance_stock as _as_mod
import currency_unit_stock as _cu_mod

_rs_mod.STOCK_DIR = _TEST_REJECTIONS_DIR
_rs_mod.MANIFEST_PATH = _TEST_REJECTIONS_DIR / "manifest.json"
_as_mod.STOCK_DIR = _TEST_ACCEPTANCES_DIR
_as_mod.MANIFEST_PATH = _TEST_ACCEPTANCES_DIR / "manifest.json"
_cu_mod.STOCK_PATH = _TEST_AUDIO_DIR / "currency_units.json"

# Temporarily patch pathlib.Path.mkdir to avoid /app/audio creation errors
_orig_mkdir = Path.mkdir

def _safe_mkdir(self, *a, **kw):
    if str(self).startswith("/app"):
        _TEST_AUDIO_DIR.mkdir(exist_ok=True)
        return
    return _orig_mkdir(self, *a, **kw)

Path.mkdir = _safe_mkdir  # type: ignore[assignment]

# Now it is safe to import main (module-level init will use our temp paths)
import main as _main_mod

Path.mkdir = _orig_mkdir  # type: ignore[assignment]
_main_mod.AUDIO_DIR = _TEST_AUDIO_DIR


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def mock_speech_gen():
    """Create a mock SpeechGenerator with common async methods."""
    gen = MagicMock()
    gen.generate_rejection_text = AsyncMock(return_value="AI overlord disapproves.")
    gen.generate_currency_unit_text = AsyncMock(return_value="test-coin")
    gen.generate_speech_text = AsyncMock(return_value="Test announcement text")
    gen.generate_feedback = AsyncMock(return_value="Thank you for completing the task.")
    gen.generate_completion_text = AsyncMock(return_value="Great job completing this task!")
    gen.generate_acceptance_text = AsyncMock(return_value="Thank you for accepting!")
    gen.llm_api_url = "http://test-llm:8000/v1"
    gen.currency_stock = None
    return gen


@pytest.fixture
def mock_voice_client():
    """Create a mock VoicevoxClient with common async methods."""
    client = MagicMock()
    # Return 48000 bytes = 1 second of audio at 24kHz 16-bit
    client.synthesize = AsyncMock(return_value=b"\x00" * 48000)
    client.save_audio = AsyncMock()
    client.base_url = "http://test-voicevox:50021"
    return client


@pytest.fixture
def tmp_stock_dir(tmp_path):
    """Create a temporary directory for rejection stock files."""
    stock_dir = tmp_path / "rejections"
    stock_dir.mkdir()
    return stock_dir


@pytest.fixture
def tmp_acceptance_dir(tmp_path):
    """Create a temporary directory for acceptance stock files."""
    stock_dir = tmp_path / "acceptances"
    stock_dir.mkdir()
    return stock_dir


@pytest.fixture
def tmp_currency_path(tmp_path):
    """Create a temporary path for currency unit stock file."""
    return tmp_path / "currency_units.json"
