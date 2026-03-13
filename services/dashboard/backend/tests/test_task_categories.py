"""Unit tests for task category classification and Stage 1.5 duplicate detection."""
import pytest

from routers.tasks import _classify_task, _TASK_CATEGORIES


class TestClassifyTask:
    """Tests for _classify_task category classification."""

    def test_device_check_keywords(self):
        cats = _classify_task("未登録デバイスの確認")
        assert "device_check" in cats

    def test_device_investigation_variant(self):
        cats = _classify_task("デバイス調査タスク", "デバイスの状態を調べてください")
        assert "device_check" in cats

    def test_temperature_keywords(self):
        cats = _classify_task("室温が高すぎます")
        assert "temperature" in cats

    def test_co2_keywords(self):
        cats = _classify_task("換気をしてください", "CO2レベルが高い")
        assert "co2" in cats

    def test_humidity_keywords(self):
        cats = _classify_task("加湿器を設置", "湿度が低い")
        assert "humidity" in cats

    def test_unrelated_task_empty(self):
        cats = _classify_task("掃除をしてください", "会議室をきれいにする")
        assert cats == set()

    def test_multiple_categories(self):
        cats = _classify_task("温度と湿度を調整してください")
        assert "temperature" in cats
        assert "humidity" in cats

    def test_category_match_is_case_insensitive(self):
        """CO2 in uppercase should match."""
        cats = _classify_task("CO2レベルが高い")
        assert "co2" in cats

    @pytest.mark.parametrize("title", [
        "未確認デバイスへの対応",
        "デバイスの登録を行う",
        "不明デバイスを調査",
        "デバイス確認タスク",
    ])
    def test_all_device_check_variants(self, title):
        cats = _classify_task(title)
        assert "device_check" in cats

    def test_legitimate_device_task_not_categorized(self):
        """A battery replacement task for a device should NOT match device_check."""
        cats = _classify_task("バッテリー交換が必要", "デバイスenv_01の電池が切れそう")
        assert "device_check" not in cats
