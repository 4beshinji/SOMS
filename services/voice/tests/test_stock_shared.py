"""Shared interface tests for all stock types (rejection, acceptance, currency).

These tests verify the common interface: count, needs_refill, is_full, is_idle,
request_started/finished, and generate_one (when full). Each test runs three
times via the ``stock_with_spec`` parametrized fixture from conftest.py.
"""
import pytest


class TestStockSharedProperties:
    """Common property tests across all stock types."""

    def test_count_empty(self, stock_with_spec):
        stock, _spec = stock_with_spec
        assert stock.count == 0

    def test_needs_refill_when_empty(self, stock_with_spec):
        stock, _spec = stock_with_spec
        assert stock.needs_refill is True

    def test_is_full_when_empty(self, stock_with_spec):
        stock, _spec = stock_with_spec
        assert stock.is_full is False

    def test_is_idle_initially(self, stock_with_spec):
        stock, _spec = stock_with_spec
        assert stock.is_idle is True

    def test_request_tracking(self, stock_with_spec):
        stock, _spec = stock_with_spec
        stock.request_started()
        assert stock.is_idle is False
        stock.request_finished()
        assert stock.is_idle is True

    def test_request_finished_clamps_to_zero(self, stock_with_spec):
        stock, _spec = stock_with_spec
        stock.request_finished()  # no prior start
        assert stock._active_requests == 0

    def test_needs_refill_false_at_threshold(self, stock_with_spec):
        stock, spec = stock_with_spec
        entries = spec.make_fake_entries(spec.refill_threshold)
        setattr(stock, spec.entries_attr, entries)
        assert stock.needs_refill is False

    def test_is_full_at_max(self, stock_with_spec):
        stock, spec = stock_with_spec
        entries = spec.make_fake_entries(spec.max_stock)
        setattr(stock, spec.entries_attr, entries)
        assert stock.is_full is True

    @pytest.mark.asyncio
    async def test_generate_one_returns_false_when_full(self, stock_with_spec):
        stock, spec = stock_with_spec
        entries = spec.make_fake_entries(spec.max_stock)
        setattr(stock, spec.entries_attr, entries)
        result = await stock.generate_one()
        assert result is False
