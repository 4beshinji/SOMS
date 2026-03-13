"""Tests for VLMPeriodicService — zone cycling, source failure handling."""
import asyncio
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vlm.periodic_service import VLMPeriodicService


class FakeImageSource:
    """Fake image source that returns a black frame."""
    def __init__(self, fail=False):
        self._fail = fail
        self.read_count = 0

    def read(self):
        self.read_count += 1
        if self._fail:
            return None
        return np.zeros((480, 640, 3), dtype=np.uint8)


class TestVLMPeriodicService:
    def test_init(self):
        analyzer = AsyncMock()
        sources = {"kitchen": FakeImageSource(), "entrance": FakeImageSource()}
        service = VLMPeriodicService(analyzer, sources, interval_sec=60)
        assert service._interval == 60

    @pytest.mark.asyncio
    async def test_cycles_through_zones(self):
        analyzer = AsyncMock()
        analyzer.request_analysis = AsyncMock(return_value={"status": "queued"})
        sources = {
            "kitchen": FakeImageSource(),
            "entrance": FakeImageSource(),
        }
        service = VLMPeriodicService(analyzer, sources, interval_sec=0.1)

        # Run for a short time then cancel
        task = asyncio.create_task(service.run())
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Both zones should have been read
        assert sources["kitchen"].read_count > 0
        assert sources["entrance"].read_count > 0
        # Analyzer should have been called with "scene" type
        for call in analyzer.request_analysis.call_args_list:
            assert call[0][1] == "scene"  # analysis_type
            assert call[0][2] in ("kitchen", "entrance")  # zone

    @pytest.mark.asyncio
    async def test_skips_failed_sources(self):
        analyzer = AsyncMock()
        analyzer.request_analysis = AsyncMock(return_value={"status": "queued"})
        sources = {
            "kitchen": FakeImageSource(fail=True),
            "entrance": FakeImageSource(fail=False),
        }
        service = VLMPeriodicService(analyzer, sources, interval_sec=0.1)

        task = asyncio.create_task(service.run())
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Kitchen should have been tried but no analysis requested
        assert sources["kitchen"].read_count > 0
        # Entrance should have been analyzed
        for call in analyzer.request_analysis.call_args_list:
            assert call[0][2] == "entrance"

    @pytest.mark.asyncio
    async def test_no_sources_returns(self):
        analyzer = AsyncMock()
        service = VLMPeriodicService(analyzer, {}, interval_sec=1)

        # Should return immediately (no infinite loop)
        task = asyncio.create_task(service.run())
        await asyncio.sleep(0.1)
        assert task.done()

    @pytest.mark.asyncio
    async def test_source_exception_handled(self):
        analyzer = AsyncMock()
        analyzer.request_analysis = AsyncMock()

        class ExplodingSource:
            def read(self):
                raise RuntimeError("camera disconnected")

        sources = {"broken": ExplodingSource(), "ok": FakeImageSource()}
        service = VLMPeriodicService(analyzer, sources, interval_sec=0.1)

        task = asyncio.create_task(service.run())
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should not have crashed — ok source should still be read
        assert sources["ok"].read_count > 0
