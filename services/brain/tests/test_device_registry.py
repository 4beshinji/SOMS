"""Unit tests for DeviceRegistry and device investigation guard."""
import time
import sys
from pathlib import Path

import pytest

# Ensure brain src is importable
BRAIN_SRC = str(Path(__file__).resolve().parent.parent / "src")
if BRAIN_SRC not in sys.path:
    sys.path.insert(0, BRAIN_SRC)

from device_registry import DeviceRegistry, DeviceInfo, TRUST_THRESHOLD_SEC


# ── DeviceRegistry.get_status_summary ────────────────────────────


class TestGetStatusSummary:
    """Untrusted devices must NOT leak into LLM-visible summaries."""

    def _make_registry_with_untrusted(self, count=3):
        reg = DeviceRegistry()
        for i in range(count):
            d = DeviceInfo(f"dev_{i}", "sensor")
            d.trusted = False
            d.last_seen = time.time()
            reg.devices[d.device_id] = d
        return reg

    def _make_registry_with_mixed(self):
        reg = DeviceRegistry()
        # 1 trusted device
        t = DeviceInfo("trusted_01", "sensor")
        t.trusted = True
        t.last_seen = time.time()
        reg.devices[t.device_id] = t
        # 2 untrusted devices
        for i in range(2):
            u = DeviceInfo(f"untrusted_{i}", "sensor")
            u.trusted = False
            u.last_seen = time.time()
            reg.devices[u.device_id] = u
        return reg

    def test_only_untrusted_returns_empty(self):
        reg = self._make_registry_with_untrusted(3)
        summary = reg.get_status_summary()
        assert summary == ""

    def test_mixed_hides_untrusted_line(self):
        reg = self._make_registry_with_mixed()
        summary = reg.get_status_summary()
        assert "未確認" not in summary
        assert "trusted_01" not in summary  # device IDs aren't in summary, just counts
        assert "デバイス合計: 1台" in summary

    def test_empty_registry_returns_empty(self):
        reg = DeviceRegistry()
        assert reg.get_status_summary() == ""


# ── DeviceRegistry.get_device_tree ───────────────────────────────


class TestGetDeviceTree:
    def test_empty_registry_no_unregistered_keyword(self):
        reg = DeviceRegistry()
        tree = reg.get_device_tree()
        assert "未登録" not in tree
        assert "登録済みデバイスなし" in tree

    def test_untrusted_devices_hidden_from_tree(self):
        reg = DeviceRegistry()
        u = DeviceInfo("untrusted_01", "sensor")
        u.trusted = False
        u.last_seen = time.time()
        reg.devices[u.device_id] = u
        tree = reg.get_device_tree()
        assert "未確認" not in tree
        assert "untrusted_01" not in tree


# ── _is_device_investigation_task ────────────────────────────────


from main import _is_device_investigation_task


class TestIsDeviceInvestigationTask:
    """Tests for the hard guard that blocks device investigation tasks."""

    @pytest.mark.parametrize("title,desc", [
        ("未登録デバイスの確認", ""),
        ("デバイス確認タスク", ""),
        ("不明デバイスの調査", "原因を調査してください"),
        ("デバイスの登録を実施", ""),
        ("未確認デバイスへの対応", ""),
        ("デバイス調査: env_03", ""),
        ("未認識デバイスの対応", "デバイスを確認"),
        ("不明なデバイスを調べてください", ""),
    ])
    def test_blocks_investigation_tasks(self, title, desc):
        assert _is_device_investigation_task(title, desc) is True

    @pytest.mark.parametrize("title,desc", [
        ("バッテリー交換: デバイスenv_01", ""),
        ("デバイスenv_01がオフライン", "再起動してください"),
        ("温度センサーの値が異常", ""),
        ("換気を実施してください", "CO2が高い"),
        ("エアコンの設定温度を下げてください", ""),
        ("デバイスのバッテリーが低下", "交換が必要"),
        ("掃除をしてください", ""),
    ])
    def test_allows_legitimate_tasks(self, title, desc):
        assert _is_device_investigation_task(title, desc) is False

    def test_requires_device_keyword(self):
        """Even if investigation keywords are present, 'デバイス' must be in text."""
        assert _is_device_investigation_task("未登録のセンサー確認", "") is False

    def test_case_insensitive_device_keyword(self):
        """Text is lowered so ASCII parts match."""
        assert _is_device_investigation_task("デバイス確認", "") is True
