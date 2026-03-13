"""Unit tests for currency_unit_stock.py — CurrencyUnitStock-specific behavior.

Shared interface tests (count, needs_refill, is_full, is_idle, request_tracking,
generate_one_when_full) live in test_stock_shared.py.
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from conftest import make_currency_stock


# ── CurrencyUnitStock: init / persistence ────────────────────────


class TestCurrencyUnitStockInit:

    def test_creates_file_on_fresh_start(self, mock_speech_gen, tmp_currency_path):
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        assert tmp_currency_path.exists()
        data = json.loads(tmp_currency_path.read_text())
        assert data == {"units": []}

    def test_loads_existing_file(self, mock_speech_gen, tmp_currency_path):
        tmp_currency_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_currency_path.write_text(json.dumps({"units": ["coin_a", "coin_b"]}))
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        assert stock.count == 2

    def test_handles_corrupt_file(self, mock_speech_gen, tmp_currency_path):
        tmp_currency_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_currency_path.write_text("CORRUPT")
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        assert stock.count == 0


# ── CurrencyUnitStock: get_random ────────────────────────────────


class TestCurrencyUnitStockGetRandom:

    def test_get_random_from_stock(self, mock_speech_gen, tmp_currency_path):
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        stock._units = ["alpha-coin", "beta-coin"]
        result = stock.get_random()
        assert result in ("alpha-coin", "beta-coin")

    def test_get_random_fallback_when_empty(self, mock_speech_gen, tmp_currency_path):
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        from currency_unit_stock import FALLBACK_UNITS
        result = stock.get_random()
        assert result in FALLBACK_UNITS

    def test_get_random_is_non_destructive(self, mock_speech_gen, tmp_currency_path):
        """get_random should NOT remove entries from stock."""
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        stock._units = ["only-coin"]
        stock.get_random()
        assert stock.count == 1


# ── CurrencyUnitStock: generate_one ──────────────────────────────


class TestCurrencyUnitStockGenerateOne:

    @pytest.mark.asyncio
    async def test_generate_one_success(self, mock_speech_gen, tmp_currency_path):
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        result = await stock.generate_one()
        assert result is True
        assert stock.count == 1
        assert stock._units[0] == "test-coin"

    @pytest.mark.asyncio
    async def test_generate_one_rejects_too_long(self, mock_speech_gen, tmp_currency_path):
        mock_speech_gen.generate_currency_unit_text = AsyncMock(
            return_value="A" * 21  # 21 chars > 20 limit
        )
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        result = await stock.generate_one()
        assert result is False
        assert stock.count == 0

    @pytest.mark.asyncio
    async def test_generate_one_rejects_empty_string(self, mock_speech_gen, tmp_currency_path):
        mock_speech_gen.generate_currency_unit_text = AsyncMock(return_value="")
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        result = await stock.generate_one()
        assert result is False

    @pytest.mark.asyncio
    async def test_generate_one_skips_duplicate(self, mock_speech_gen, tmp_currency_path):
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        stock._units = ["test-coin"]  # Already exists
        result = await stock.generate_one()
        assert result is False
        assert stock.count == 1  # Unchanged

    @pytest.mark.asyncio
    async def test_generate_one_handles_llm_error(self, mock_speech_gen, tmp_currency_path):
        mock_speech_gen.generate_currency_unit_text = AsyncMock(
            side_effect=RuntimeError("LLM error")
        )
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        result = await stock.generate_one()
        assert result is False


# ── CurrencyUnitStock: clear_all ─────────────────────────────────


class TestCurrencyUnitStockClearAll:

    @pytest.mark.asyncio
    async def test_clear_all(self, mock_speech_gen, tmp_currency_path):
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        stock._units = ["a", "b", "c"]
        await stock.clear_all()
        assert stock.count == 0
        data = json.loads(tmp_currency_path.read_text())
        assert data == {"units": []}


# ── idle_currency_generation_loop ────────────────────────────────


class TestIdleCurrencyLoop:

    @pytest.mark.asyncio
    async def test_loop_cancellation(self, mock_speech_gen, tmp_currency_path):
        stock = make_currency_stock(mock_speech_gen, tmp_currency_path)
        from currency_unit_stock import idle_currency_generation_loop

        with patch("currency_unit_stock.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            call_count = 0
            async def sleep_side_effect(seconds):
                nonlocal call_count
                call_count += 1
                if call_count >= 2:
                    raise asyncio.CancelledError()
            mock_sleep.side_effect = sleep_side_effect
            # Should not raise
            await idle_currency_generation_loop(stock)
