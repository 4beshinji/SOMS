"""Unit tests for acceptance_stock.py — AcceptanceStock-specific behavior.

Shared interface tests (count, needs_refill, is_full, is_idle, request_tracking,
generate_one_when_full) live in test_stock_shared.py.
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from conftest import make_acceptance_stock


# ── AcceptanceStock: get_random ──────────────────────────────────


class TestAcceptanceStockGetRandom:

    @pytest.mark.asyncio
    async def test_get_random_returns_none_when_empty(self, mock_speech_gen, mock_voice_client, tmp_acceptance_dir):
        stock = make_acceptance_stock(mock_speech_gen, mock_voice_client, tmp_acceptance_dir)
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
