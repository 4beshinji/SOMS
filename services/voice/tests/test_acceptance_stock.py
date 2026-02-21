"""Unit tests for acceptance_stock.py — AcceptanceStock class and idle_generation_loop."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── AcceptanceStock: properties ──────────────────────────────────


class TestAcceptanceStockProperties:
    """Test basic property behaviour of AcceptanceStock."""

    def _make_stock(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        """Helper: build an AcceptanceStock whose paths point at tmp dir."""
        with patch("acceptance_stock.STOCK_DIR", tmp_acceptance_dir), \
             patch("acceptance_stock.MANIFEST_PATH", tmp_acceptance_dir / "manifest.json"):
            from acceptance_stock import AcceptanceStock
            return AcceptanceStock(mock_speech_gen, mock_voice_client)

    def test_count_empty(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        stock = self._make_stock(mock_speech_gen, mock_voice_client, tmp_acceptance_dir)
        assert stock.count == 0

    def test_needs_refill_when_empty(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        stock = self._make_stock(mock_speech_gen, mock_voice_client, tmp_acceptance_dir)
        assert stock.needs_refill is True

    def test_is_full_when_empty(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        stock = self._make_stock(mock_speech_gen, mock_voice_client, tmp_acceptance_dir)
        assert stock.is_full is False

    def test_is_idle_initially(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        stock = self._make_stock(mock_speech_gen, mock_voice_client, tmp_acceptance_dir)
        assert stock.is_idle is True

    def test_request_tracking(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        stock = self._make_stock(mock_speech_gen, mock_voice_client, tmp_acceptance_dir)
        stock.request_started()
        assert stock.is_idle is False
        stock.request_finished()
        assert stock.is_idle is True

    def test_is_full_at_max(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        stock = self._make_stock(mock_speech_gen, mock_voice_client, tmp_acceptance_dir)
        stock._entries = [{"id": str(i)} for i in range(50)]
        assert stock.is_full is True

    def test_needs_refill_threshold(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        """needs_refill should be False when stock >= REFILL_THRESHOLD (20)."""
        stock = self._make_stock(mock_speech_gen, mock_voice_client, tmp_acceptance_dir)
        stock._entries = [{"id": str(i)} for i in range(20)]
        assert stock.needs_refill is False


# ── AcceptanceStock: get_random ──────────────────────────────────


class TestAcceptanceStockGetRandom:

    @pytest.mark.asyncio
    async def test_get_random_returns_none_when_empty(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        with patch("acceptance_stock.STOCK_DIR", tmp_acceptance_dir), \
             patch("acceptance_stock.MANIFEST_PATH", tmp_acceptance_dir / "manifest.json"):
            from acceptance_stock import AcceptanceStock
            stock = AcceptanceStock(mock_speech_gen, mock_voice_client)
        result = await stock.get_random()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_random_pops_entry(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        manifest = tmp_acceptance_dir / "manifest.json"
        (tmp_acceptance_dir / "acc_a.mp3").write_bytes(b"\x00")
        manifest.write_text(json.dumps({
            "entries": [{"id": "a", "text": "acceptance text", "audio_file": "acc_a.mp3"}]
        }))
        with patch("acceptance_stock.STOCK_DIR", tmp_acceptance_dir), \
             patch("acceptance_stock.MANIFEST_PATH", manifest):
            from acceptance_stock import AcceptanceStock
            stock = AcceptanceStock(mock_speech_gen, mock_voice_client)
        assert stock.count == 1
        result = await stock.get_random()
        assert result is not None
        assert result["text"] == "acceptance text"
        assert result["audio_url"] == "/audio/acceptances/acc_a.mp3"
        assert stock.count == 0


# ── AcceptanceStock: generate_one ────────────────────────────────


class TestAcceptanceStockGenerateOne:

    @pytest.mark.asyncio
    async def test_generate_one_success(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        manifest = tmp_acceptance_dir / "manifest.json"
        with patch("acceptance_stock.STOCK_DIR", tmp_acceptance_dir), \
             patch("acceptance_stock.MANIFEST_PATH", manifest):
            from acceptance_stock import AcceptanceStock
            stock = AcceptanceStock(mock_speech_gen, mock_voice_client)
            with patch("acceptance_stock.VoicevoxClient") as MockVC:
                MockVC.pick_speaker.return_value = 48
                result = await stock.generate_one()
        assert result is True
        assert stock.count == 1

    @pytest.mark.asyncio
    async def test_generate_one_returns_false_when_full(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        manifest = tmp_acceptance_dir / "manifest.json"
        with patch("acceptance_stock.STOCK_DIR", tmp_acceptance_dir), \
             patch("acceptance_stock.MANIFEST_PATH", manifest):
            from acceptance_stock import AcceptanceStock
            stock = AcceptanceStock(mock_speech_gen, mock_voice_client)
            stock._entries = [{"id": str(i)} for i in range(50)]
            result = await stock.generate_one()
        assert result is False


# ── AcceptanceStock: clear_all ───────────────────────────────────


class TestAcceptanceStockClearAll:

    @pytest.mark.asyncio
    async def test_clear_all(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        manifest = tmp_acceptance_dir / "manifest.json"
        audio_file = tmp_acceptance_dir / "acc_c.mp3"
        audio_file.write_bytes(b"\x00")
        manifest.write_text(json.dumps({
            "entries": [{"id": "c", "text": "text_c", "audio_file": "acc_c.mp3"}]
        }))
        with patch("acceptance_stock.STOCK_DIR", tmp_acceptance_dir), \
             patch("acceptance_stock.MANIFEST_PATH", manifest):
            from acceptance_stock import AcceptanceStock
            stock = AcceptanceStock(mock_speech_gen, mock_voice_client)
            assert stock.count == 1
            await stock.clear_all()
            assert stock.count == 0
            assert not audio_file.exists()
