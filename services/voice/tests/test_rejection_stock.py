"""Unit tests for rejection_stock.py — RejectionStock-specific behavior.

Shared interface tests (count, needs_refill, is_full, is_idle, request_tracking,
generate_one_when_full) live in test_stock_shared.py.
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from conftest import make_rejection_stock


# ── RejectionStock: init / manifest persistence ─────────────────


class TestRejectionStockInit:
    """Test _init_storage and manifest loading."""

    def test_creates_manifest_on_fresh_start(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        manifest = tmp_stock_dir / "manifest.json"
        with patch("rejection_stock.STOCK_DIR", tmp_stock_dir), \
             patch("rejection_stock.MANIFEST_PATH", manifest):
            from rejection_stock import RejectionStock
            stock = RejectionStock(mock_speech_gen, mock_voice_client)
        assert manifest.exists()
        data = json.loads(manifest.read_text())
        assert data == {"entries": []}

    def test_loads_existing_manifest(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        manifest = tmp_stock_dir / "manifest.json"
        # Pre-create an audio file so the entry is not pruned
        (tmp_stock_dir / "rej_01.mp3").write_bytes(b"\x00")
        manifest.write_text(json.dumps({
            "entries": [{"id": "01", "text": "hello", "audio_file": "rej_01.mp3"}]
        }))
        with patch("rejection_stock.STOCK_DIR", tmp_stock_dir), \
             patch("rejection_stock.MANIFEST_PATH", manifest):
            from rejection_stock import RejectionStock
            stock = RejectionStock(mock_speech_gen, mock_voice_client)
        assert stock.count == 1

    def test_prunes_entries_with_missing_audio(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        manifest = tmp_stock_dir / "manifest.json"
        # No audio file on disk for this entry
        manifest.write_text(json.dumps({
            "entries": [{"id": "01", "text": "hello", "audio_file": "missing.mp3"}]
        }))
        with patch("rejection_stock.STOCK_DIR", tmp_stock_dir), \
             patch("rejection_stock.MANIFEST_PATH", manifest):
            from rejection_stock import RejectionStock
            stock = RejectionStock(mock_speech_gen, mock_voice_client)
        assert stock.count == 0

    def test_handles_corrupt_manifest(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        manifest = tmp_stock_dir / "manifest.json"
        manifest.write_text("NOT VALID JSON")
        with patch("rejection_stock.STOCK_DIR", tmp_stock_dir), \
             patch("rejection_stock.MANIFEST_PATH", manifest):
            from rejection_stock import RejectionStock
            stock = RejectionStock(mock_speech_gen, mock_voice_client)
        assert stock.count == 0


# ── RejectionStock: get_random ───────────────────────────────────


class TestRejectionStockGetRandom:
    """Test the get_random method."""

    @pytest.mark.asyncio
    async def test_get_random_returns_none_when_empty(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        stock = make_rejection_stock(mock_speech_gen, mock_voice_client, tmp_stock_dir)
        result = await stock.get_random()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_random_pops_entry(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        manifest = tmp_stock_dir / "manifest.json"
        (tmp_stock_dir / "rej_a.mp3").write_bytes(b"\x00")
        manifest.write_text(json.dumps({
            "entries": [{"id": "a", "text": "rejection text", "audio_file": "rej_a.mp3"}]
        }))
        with patch("rejection_stock.STOCK_DIR", tmp_stock_dir), \
             patch("rejection_stock.MANIFEST_PATH", manifest):
            from rejection_stock import RejectionStock
            stock = RejectionStock(mock_speech_gen, mock_voice_client)
        assert stock.count == 1
        result = await stock.get_random()
        assert result is not None
        assert result["text"] == "rejection text"
        assert result["audio_url"] == "/audio/rejections/rej_a.mp3"
        assert stock.count == 0

    @pytest.mark.asyncio
    async def test_get_random_restores_on_save_failure(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        manifest = tmp_stock_dir / "manifest.json"
        (tmp_stock_dir / "rej_b.mp3").write_bytes(b"\x00")
        manifest.write_text(json.dumps({
            "entries": [{"id": "b", "text": "text_b", "audio_file": "rej_b.mp3"}]
        }))
        with patch("rejection_stock.STOCK_DIR", tmp_stock_dir), \
             patch("rejection_stock.MANIFEST_PATH", manifest):
            from rejection_stock import RejectionStock
            stock = RejectionStock(mock_speech_gen, mock_voice_client)
            # Make manifest save fail
            with patch.object(stock, "_save_manifest", side_effect=IOError("disk full")):
                result = await stock.get_random()
        # Entry should be restored on failure
        assert result is None
        assert stock.count == 1


# ── RejectionStock: clear_all ────────────────────────────────────


class TestRejectionStockClearAll:

    @pytest.mark.asyncio
    async def test_clear_all_removes_entries_and_files(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        manifest = tmp_stock_dir / "manifest.json"
        audio_file = tmp_stock_dir / "rej_c.mp3"
        audio_file.write_bytes(b"\x00")
        manifest.write_text(json.dumps({
            "entries": [{"id": "c", "text": "text_c", "audio_file": "rej_c.mp3"}]
        }))
        with patch("rejection_stock.STOCK_DIR", tmp_stock_dir), \
             patch("rejection_stock.MANIFEST_PATH", manifest):
            from rejection_stock import RejectionStock
            stock = RejectionStock(mock_speech_gen, mock_voice_client)
            assert stock.count == 1
            await stock.clear_all()
            assert stock.count == 0
            assert not audio_file.exists()


# ── RejectionStock: generate_one ─────────────────────────────────


class TestRejectionStockGenerateOne:

    @pytest.mark.asyncio
    async def test_generate_one_success(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        manifest = tmp_stock_dir / "manifest.json"
        with patch("rejection_stock.STOCK_DIR", tmp_stock_dir), \
             patch("rejection_stock.MANIFEST_PATH", manifest):
            from rejection_stock import RejectionStock
            stock = RejectionStock(mock_speech_gen, mock_voice_client)
            result = await stock.generate_one()
        assert result is True
        assert stock.count == 1
        assert stock._entries[0]["text"] == "AI overlord disapproves."

    @pytest.mark.asyncio
    async def test_generate_one_returns_false_on_llm_error(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        manifest = tmp_stock_dir / "manifest.json"
        mock_speech_gen.generate_rejection_text = AsyncMock(side_effect=RuntimeError("LLM down"))
        with patch("rejection_stock.STOCK_DIR", tmp_stock_dir), \
             patch("rejection_stock.MANIFEST_PATH", manifest):
            from rejection_stock import RejectionStock
            stock = RejectionStock(mock_speech_gen, mock_voice_client)
            result = await stock.generate_one()
        assert result is False
        assert stock.count == 0

    @pytest.mark.asyncio
    async def test_generate_one_evicts_oldest_when_over_limit(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        """If entries somehow reach MAX_STOCK, generate_one evicts oldest."""
        manifest = tmp_stock_dir / "manifest.json"
        with patch("rejection_stock.STOCK_DIR", tmp_stock_dir), \
             patch("rejection_stock.MANIFEST_PATH", manifest):
            from rejection_stock import RejectionStock
            stock = RejectionStock(mock_speech_gen, mock_voice_client)
            # Manually set to 99 (below MAX but generate will push to 100)
            stock._entries = [
                {"id": str(i), "text": f"t{i}", "audio_file": f"f{i}.mp3"}
                for i in range(99)
            ]
            result = await stock.generate_one()
        assert result is True
        assert stock.count == 100


# ── idle_generation_loop ─────────────────────────────────────────


class TestIdleGenerationLoop:

    @pytest.mark.asyncio
    async def test_loop_cancellation(self, mock_speech_gen, mock_voice_client, tmp_stock_dir):
        """The idle loop should handle CancelledError gracefully."""
        manifest = tmp_stock_dir / "manifest.json"
        with patch("rejection_stock.STOCK_DIR", tmp_stock_dir), \
             patch("rejection_stock.MANIFEST_PATH", manifest):
            from rejection_stock import RejectionStock, idle_generation_loop
            stock = RejectionStock(mock_speech_gen, mock_voice_client)

        with patch("rejection_stock.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # After the initial warm-up sleep, cancel the task
            call_count = 0
            async def sleep_side_effect(seconds):
                nonlocal call_count
                call_count += 1
                if call_count >= 2:
                    raise asyncio.CancelledError()
            mock_sleep.side_effect = sleep_side_effect

            # Should not raise
            await idle_generation_loop(stock)
