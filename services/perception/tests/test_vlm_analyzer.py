"""Tests for VLMAnalyzer — cooldown logic, MQTT publishing, async execution."""
import asyncio
import time
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vlm.vlm_client import VLMResponse
from vlm.vlm_analyzer import VLMAnalyzer, DEFAULT_COOLDOWNS


def _make_analyzer(cooldowns=None, enabled=True):
    """Create a VLMAnalyzer with mocked dependencies."""
    mock_client = AsyncMock()
    mock_client.analyze = AsyncMock(return_value=VLMResponse(
        content="テスト分析結果",
        model="qwen3-vl:8b",
        latency_sec=1.5,
    ))
    mock_publisher = AsyncMock()
    mock_publisher.publish = AsyncMock()

    analyzer = VLMAnalyzer(
        vlm_client=mock_client,
        publisher=mock_publisher,
        cooldowns=cooldowns,
        enabled=enabled,
    )
    return analyzer, mock_client, mock_publisher


class TestCooldown:
    def test_first_request_allowed(self):
        analyzer, _, _ = _make_analyzer()
        assert analyzer._is_cooled_down("kitchen", "scene") is True

    def test_second_request_blocked(self):
        analyzer, _, _ = _make_analyzer()
        analyzer._last_analysis["kitchen:scene"] = time.time()
        assert analyzer._is_cooled_down("kitchen", "scene") is False

    def test_different_zone_allowed(self):
        analyzer, _, _ = _make_analyzer()
        analyzer._last_analysis["kitchen:scene"] = time.time()
        assert analyzer._is_cooled_down("entrance", "scene") is True

    def test_different_type_allowed(self):
        analyzer, _, _ = _make_analyzer()
        analyzer._last_analysis["kitchen:scene"] = time.time()
        assert analyzer._is_cooled_down("kitchen", "fall_candidate") is True

    def test_expired_cooldown_allowed(self):
        analyzer, _, _ = _make_analyzer(cooldowns={"scene": 1})
        analyzer._last_analysis["kitchen:scene"] = time.time() - 2
        assert analyzer._is_cooled_down("kitchen", "scene") is True

    def test_default_cooldowns(self):
        assert DEFAULT_COOLDOWNS["scene"] == 300
        assert DEFAULT_COOLDOWNS["fall_candidate"] == 30


class TestRequestAnalysis:
    @pytest.mark.asyncio
    async def test_disabled_returns_none(self):
        analyzer, _, _ = _make_analyzer(enabled=False)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = await analyzer.request_analysis(frame, "scene", "kitchen")
        assert result is None

    @pytest.mark.asyncio
    async def test_cooled_down_returns_none(self):
        analyzer, _, _ = _make_analyzer()
        analyzer._last_analysis["kitchen:scene"] = time.time()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = await analyzer.request_analysis(frame, "scene", "kitchen")
        assert result is None

    @pytest.mark.asyncio
    async def test_allowed_returns_queued(self):
        analyzer, _, _ = _make_analyzer()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = await analyzer.request_analysis(frame, "scene", "kitchen")
        assert result is not None
        assert result["status"] == "queued"

    @pytest.mark.asyncio
    async def test_marks_cooldown_immediately(self):
        analyzer, _, _ = _make_analyzer()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        await analyzer.request_analysis(frame, "scene", "kitchen")
        assert "kitchen:scene" in analyzer._last_analysis

    @pytest.mark.asyncio
    async def test_publishes_to_mqtt(self):
        analyzer, mock_client, mock_publisher = _make_analyzer()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        await analyzer.request_analysis(frame, "scene", "kitchen", {"trigger": "periodic"})
        # Let the background task complete
        await asyncio.sleep(0.1)
        mock_publisher.publish.assert_awaited()
        call_args = mock_publisher.publish.call_args
        assert call_args[0][0] == "office/kitchen/vlm/scene"
        payload = call_args[0][1]
        assert payload["analysis_type"] == "scene"
        assert payload["content"] == "テスト分析結果"

    @pytest.mark.asyncio
    async def test_duplicate_inflight_blocked(self):
        analyzer, mock_client, _ = _make_analyzer()
        # Make client slow
        async def slow_analyze(*args, **kwargs):
            await asyncio.sleep(1)
            return VLMResponse(content="result", model="test", latency_sec=1.0)
        mock_client.analyze = slow_analyze

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        r1 = await analyzer.request_analysis(frame, "scene", "kitchen")
        # Immediately try again — should be blocked by pending
        analyzer._last_analysis.pop("kitchen:scene")  # Remove cooldown to test pending check
        r2 = await analyzer.request_analysis(frame, "scene", "kitchen")
        assert r1 is not None
        assert r2 is None

    @pytest.mark.asyncio
    async def test_error_response_no_publish(self):
        analyzer, mock_client, mock_publisher = _make_analyzer()
        mock_client.analyze = AsyncMock(return_value=VLMResponse(
            error="timeout", model="test", latency_sec=30.0,
        ))
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        await analyzer.request_analysis(frame, "scene", "kitchen")
        await asyncio.sleep(0.1)
        mock_publisher.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pending_cleared_after_completion(self):
        analyzer, _, _ = _make_analyzer()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        await analyzer.request_analysis(frame, "scene", "kitchen")
        await asyncio.sleep(0.1)
        assert "kitchen:scene" not in analyzer._pending
