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
# pydub is used by tts_provider.py but is not installed in the test venv.
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
    """Create a mock TTSProvider with common async methods."""
    from tts_provider import AudioResult

    client = MagicMock()
    # Return AudioResult with 48000 bytes = 1 second of audio at 24kHz 16-bit
    client.synthesize = AsyncMock(
        return_value=AudioResult(audio_data=b"\x00" * 48000)
    )
    client.save_audio = AsyncMock()
    client.name = "voicevox"
    client.get_speaker_name = AsyncMock(return_value="ナースロボ＿タイプＴ")
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


# ── Shared stock factory helpers ──────────────────────────────────


def make_rejection_stock(mock_speech_gen, mock_voice_client, tmp_dir):
    """Build a RejectionStock whose paths point at tmp_dir."""
    with patch("rejection_stock.STOCK_DIR", tmp_dir), \
         patch("rejection_stock.MANIFEST_PATH", tmp_dir / "manifest.json"):
        from rejection_stock import RejectionStock
        return RejectionStock(mock_speech_gen, mock_voice_client)


def make_acceptance_stock(mock_speech_gen, mock_voice_client, tmp_dir):
    """Build an AcceptanceStock whose paths point at tmp_dir."""
    with patch("acceptance_stock.STOCK_DIR", tmp_dir), \
         patch("acceptance_stock.MANIFEST_PATH", tmp_dir / "manifest.json"):
        from acceptance_stock import AcceptanceStock
        return AcceptanceStock(mock_speech_gen, mock_voice_client)


def make_currency_stock(mock_speech_gen, tmp_path):
    """Build a CurrencyUnitStock whose file path points at tmp_path."""
    with patch("currency_unit_stock.STOCK_PATH", tmp_path):
        from currency_unit_stock import CurrencyUnitStock
        return CurrencyUnitStock(mock_speech_gen)


class StockSpec:
    """Metadata for a stock type, used by parametrized shared tests."""

    def __init__(self, name, max_stock, refill_threshold, entries_attr):
        self.name = name
        self.max_stock = max_stock
        self.refill_threshold = refill_threshold
        self.entries_attr = entries_attr

    def make_fake_entries(self, count):
        """Create fake entries appropriate for the stock type."""
        if self.entries_attr == "_units":
            return [f"unit_{i}" for i in range(count)]
        return [{"id": str(i), "text": f"t{i}", "audio_file": f"f{i}.mp3"} for i in range(count)]


REJECTION_SPEC = StockSpec("rejection", max_stock=100, refill_threshold=80, entries_attr="_entries")
ACCEPTANCE_SPEC = StockSpec("acceptance", max_stock=50, refill_threshold=20, entries_attr="_entries")
CURRENCY_SPEC = StockSpec("currency", max_stock=50, refill_threshold=30, entries_attr="_units")


@pytest.fixture(params=["rejection", "acceptance", "currency"])
def stock_with_spec(request, mock_speech_gen, mock_voice_client, tmp_path):
    """
    Parametrized fixture yielding (stock_instance, StockSpec) for each stock type.
    Runs each test 3 times — once per stock type.
    """
    if request.param == "rejection":
        tmp_dir = tmp_path / "rejections"
        tmp_dir.mkdir()
        stock = make_rejection_stock(mock_speech_gen, mock_voice_client, tmp_dir)
        return stock, REJECTION_SPEC
    elif request.param == "acceptance":
        tmp_dir = tmp_path / "acceptances"
        tmp_dir.mkdir()
        stock = make_acceptance_stock(mock_speech_gen, mock_voice_client, tmp_dir)
        return stock, ACCEPTANCE_SPEC
    else:
        currency_path = tmp_path / "currency_units.json"
        stock = make_currency_stock(mock_speech_gen, currency_path)
        return stock, CURRENCY_SPEC
