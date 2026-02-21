"""Unit tests for main.py — FastAPI endpoint handlers.

Tests patch the module-level globals in main.py so that no real
VOICEVOX / LLM / filesystem calls are made.

conftest.py handles redirecting all filesystem paths to a temp directory
before main.py is first imported, so module-level init is safe.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import main as main_mod


# ── estimate_audio_duration ──────────────────────────────────────


class TestEstimateAudioDuration:

    def test_one_second(self):
        assert main_mod.estimate_audio_duration(b"\x00" * 48000) == 1.0

    def test_zero_bytes(self):
        assert main_mod.estimate_audio_duration(b"") == 0.0

    def test_half_second(self):
        assert main_mod.estimate_audio_duration(b"\x00" * 24000) == 0.5


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path):
    """Create a TestClient with all external dependencies mocked."""
    from fastapi.testclient import TestClient

    audio_tmp = tmp_path / "audio"
    audio_tmp.mkdir()

    # Store originals
    orig_voice = main_mod.voice_client
    orig_speech = main_mod.speech_gen
    orig_rejection = main_mod.rejection_stock
    orig_acceptance = main_mod.acceptance_stock
    orig_currency = main_mod.currency_unit_stock
    orig_audio_dir = main_mod.AUDIO_DIR

    # Create mocks
    mock_voice = MagicMock()
    mock_voice.synthesize = AsyncMock(return_value=b"\x00" * 48000)
    mock_voice.save_audio = AsyncMock()
    mock_voice.base_url = "http://test-voicevox:50021"

    mock_speech = MagicMock()
    mock_speech.generate_speech_text = AsyncMock(return_value="Generated announcement")
    mock_speech.generate_feedback = AsyncMock(return_value="Thank you!")
    mock_speech.generate_rejection_text = AsyncMock(return_value="AI is disappointed.")
    mock_speech.generate_acceptance_text = AsyncMock(return_value="Thank you for accepting!")
    mock_speech.generate_completion_text = AsyncMock(return_value="Task completed well!")
    mock_speech.llm_api_url = "http://test-llm:8000/v1"

    mock_rejection = MagicMock()
    mock_rejection.request_started = MagicMock()
    mock_rejection.request_finished = MagicMock()
    mock_rejection.get_random = AsyncMock(return_value=None)
    mock_rejection.clear_all = AsyncMock()
    mock_rejection.count = 5
    mock_rejection.is_idle = True
    mock_rejection.needs_refill = True

    mock_acceptance = MagicMock()
    mock_acceptance.request_started = MagicMock()
    mock_acceptance.request_finished = MagicMock()
    mock_acceptance.get_random = AsyncMock(return_value=None)
    mock_acceptance.clear_all = AsyncMock()
    mock_acceptance.count = 7
    mock_acceptance.is_idle = True
    mock_acceptance.needs_refill = True

    mock_currency = MagicMock()
    mock_currency.request_started = MagicMock()
    mock_currency.request_finished = MagicMock()
    mock_currency.get_random = MagicMock(return_value="test-points")
    mock_currency.clear_all = AsyncMock()
    mock_currency.count = 3
    mock_currency.needs_refill = True

    main_mod.voice_client = mock_voice
    main_mod.speech_gen = mock_speech
    main_mod.rejection_stock = mock_rejection
    main_mod.acceptance_stock = mock_acceptance
    main_mod.currency_unit_stock = mock_currency
    main_mod.AUDIO_DIR = audio_tmp

    # Disable lifespan background tasks
    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    main_mod.app.router.lifespan_context = noop_lifespan

    tc = TestClient(main_mod.app)
    yield tc, mock_voice, mock_speech, mock_rejection, mock_acceptance, mock_currency, audio_tmp

    # Restore
    main_mod.voice_client = orig_voice
    main_mod.speech_gen = orig_speech
    main_mod.rejection_stock = orig_rejection
    main_mod.acceptance_stock = orig_acceptance
    main_mod.currency_unit_stock = orig_currency
    main_mod.AUDIO_DIR = orig_audio_dir


# ── Root ─────────────────────────────────────────────────────────


class TestRootEndpoint:

    def test_root(self, client):
        tc, *_ = client
        resp = tc.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["service"] == "SOMS Voice Service"


# ── Synthesize ───────────────────────────────────────────────────


class TestSynthesizeEndpoint:

    def test_synthesize_success(self, client):
        tc, mock_voice, mock_speech, mock_rejection, mock_acceptance, mock_currency, tmp = client
        resp = tc.post("/api/voice/synthesize", json={"text": "Hello world"})
        assert resp.status_code == 200
        data = resp.json()
        assert "audio_url" in data
        assert data["text_generated"] == "Hello world"
        assert data["duration_seconds"] == 1.0
        mock_rejection.request_started.assert_called()
        mock_rejection.request_finished.assert_called()
        mock_acceptance.request_started.assert_called()
        mock_acceptance.request_finished.assert_called()
        mock_currency.request_started.assert_called()
        mock_currency.request_finished.assert_called()

    def test_synthesize_voicevox_error(self, client):
        tc, mock_voice, *_ = client
        mock_voice.synthesize = AsyncMock(side_effect=RuntimeError("VOICEVOX down"))
        resp = tc.post("/api/voice/synthesize", json={"text": "Hello"})
        assert resp.status_code == 500


# ── Announce ─────────────────────────────────────────────────────


class TestAnnounceEndpoint:

    def test_announce_success(self, client):
        tc, mock_voice, mock_speech, *_ = client
        payload = {
            "task": {
                "title": "Refill coffee",
                "description": "Coffee beans need refilling",
                "bounty_gold": 100,
                "urgency": 2,
            }
        }
        resp = tc.post("/api/voice/announce", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["text_generated"] == "Generated announcement"
        assert data["duration_seconds"] == 1.0
        mock_speech.generate_speech_text.assert_called_once()

    def test_announce_llm_error(self, client):
        tc, mock_voice, mock_speech, *_ = client
        mock_speech.generate_speech_text = AsyncMock(side_effect=RuntimeError("LLM down"))
        payload = {"task": {"title": "Test task"}}
        resp = tc.post("/api/voice/announce", json=payload)
        assert resp.status_code == 500


# ── Feedback ─────────────────────────────────────────────────────


class TestFeedbackEndpoint:

    def test_feedback_task_completed(self, client):
        tc, mock_voice, mock_speech, *_ = client
        resp = tc.post("/api/voice/feedback/task_completed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["text_generated"] == "Thank you!"

    def test_feedback_error(self, client):
        tc, mock_voice, mock_speech, *_ = client
        mock_speech.generate_feedback = AsyncMock(side_effect=RuntimeError("fail"))
        resp = tc.post("/api/voice/feedback/task_completed")
        assert resp.status_code == 500


# ── Announce with Completion ─────────────────────────────────────


class TestAnnounceWithCompletionEndpoint:

    def test_dual_voice_success(self, client):
        tc, mock_voice, mock_speech, *_ = client
        payload = {
            "task": {
                "title": "Clean kitchen",
                "description": "Wipe counters",
                "bounty_gold": 50,
            }
        }
        with patch("main.VoicevoxClient") as MockVC:
            MockVC.pick_speaker.return_value = 48
            resp = tc.post("/api/voice/announce_with_completion", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "announcement_audio_url" in data
        assert "completion_audio_url" in data
        assert data["announcement_text"] == "Generated announcement"
        assert data["completion_text"] == "Task completed well!"


# ── Rejection endpoints ──────────────────────────────────────────


class TestRejectionEndpoints:

    def test_rejection_random_from_stock(self, client):
        tc, mock_voice, mock_speech, mock_rejection, *_ = client
        mock_rejection.get_random = AsyncMock(
            return_value={"audio_url": "/audio/rejections/rej.mp3", "text": "Hmph"}
        )
        resp = tc.get("/api/voice/rejection/random")
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "Hmph"

    def test_rejection_random_fallback_on_demand(self, client):
        tc, mock_voice, mock_speech, mock_rejection, mock_acceptance, mock_currency, tmp = client
        mock_rejection.get_random = AsyncMock(return_value=None)
        with patch("main.VoicevoxClient") as MockVC:
            MockVC.pick_speaker.return_value = 46
            resp = tc.get("/api/voice/rejection/random")
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "AI is disappointed."

    def test_rejection_status(self, client):
        tc, mock_voice, mock_speech, mock_rejection, *_ = client
        resp = tc.get("/api/voice/rejection/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stock_count"] == 5
        assert data["max_stock"] == 100

    def test_rejection_clear(self, client):
        tc, mock_voice, mock_speech, mock_rejection, *_ = client
        resp = tc.post("/api/voice/rejection/clear")
        assert resp.status_code == 200
        mock_rejection.clear_all.assert_called_once()


# ── Acceptance endpoints ─────────────────────────────────────────


class TestAcceptanceEndpoints:

    def test_acceptance_random_from_stock(self, client):
        tc, mock_voice, mock_speech, mock_rejection, mock_acceptance, *_ = client
        mock_acceptance.get_random = AsyncMock(
            return_value={"audio_url": "/audio/acceptances/acc.mp3", "text": "Yay!"}
        )
        resp = tc.get("/api/voice/acceptance/random")
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "Yay!"

    def test_acceptance_status(self, client):
        tc, mock_voice, mock_speech, mock_rejection, mock_acceptance, *_ = client
        resp = tc.get("/api/voice/acceptance/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stock_count"] == 7
        assert data["max_stock"] == 50

    def test_acceptance_clear(self, client):
        tc, mock_voice, mock_speech, mock_rejection, mock_acceptance, *_ = client
        resp = tc.post("/api/voice/acceptance/clear")
        assert resp.status_code == 200
        mock_acceptance.clear_all.assert_called_once()


# ── Currency unit endpoints ──────────────────────────────────────


class TestCurrencyUnitEndpoints:

    def test_currency_status(self, client):
        tc, mock_voice, mock_speech, mock_rejection, mock_acceptance, mock_currency, *_ = client
        resp = tc.get("/api/voice/currency-units/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stock_count"] == 3
        assert data["max_stock"] == 50
        assert data["sample"] == "test-points"

    def test_currency_clear(self, client):
        tc, mock_voice, mock_speech, mock_rejection, mock_acceptance, mock_currency, *_ = client
        resp = tc.post("/api/voice/currency-units/clear")
        assert resp.status_code == 200
        mock_currency.clear_all.assert_called_once()


# ── Audio serving ────────────────────────────────────────────────


class TestAudioServing:

    def test_serve_audio_not_found(self, client):
        tc, *_ = client
        resp = tc.get("/audio/nonexistent.mp3")
        assert resp.status_code == 404

    def test_serve_audio_exists(self, client):
        tc, mock_voice, mock_speech, mock_rejection, mock_acceptance, mock_currency, audio_tmp = client
        audio_file = audio_tmp / "test_audio.mp3"
        audio_file.write_bytes(b"\xff\xfb\x90\x00" * 100)
        resp = tc.get("/audio/test_audio.mp3")
        assert resp.status_code == 200

    def test_serve_rejection_audio_not_found(self, client):
        tc, *_ = client
        resp = tc.get("/audio/rejections/nonexistent.mp3")
        assert resp.status_code == 404

    def test_serve_acceptance_audio_not_found(self, client):
        tc, *_ = client
        resp = tc.get("/audio/acceptances/nonexistent.mp3")
        assert resp.status_code == 404
