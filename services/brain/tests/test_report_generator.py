"""Unit tests for ReportGenerator (prompt building and parsing)."""
import pytest

from conftest import make_zone_state

import os
os.environ.setdefault("REPORT_LLM_MODEL", "test-model")

from report_generator import ReportGenerator
from spatial_config import SpatialConfig, ZoneGeometry, DevicePosition, BuildingConfig


def _make_spatial_config():
    """Create a minimal spatial config for testing."""
    return SpatialConfig(
        building=BuildingConfig(name="Test Office"),
        zones={
            "zone_a": ZoneGeometry(
                display_name="テストゾーンA",
                area_m2=20.0,
                floor=1,
            ),
            "zone_b": ZoneGeometry(
                display_name="テストゾーンB",
                area_m2=15.0,
                floor=1,
            ),
        },
        devices={
            "sensor_01": DevicePosition(
                zone="zone_a",
                type="temp_humidity",
                channels=["temperature", "humidity"],
                label="温湿度センサー1",
                context="テストゾーンAの窓際に設置。外気の影響を受けやすい",
            ),
            "sensor_02": DevicePosition(
                zone="zone_a",
                type="illuminance",
                channels=["illuminance"],
                label="照度センサー",
            ),
            "env_01": DevicePosition(
                zone="zone_b",
                type="mhz19c,bme680",
                channels=["co2", "temperature", "humidity", "pressure"],
                label="環境センサー",
                context="テストゾーンBのCO2・温湿度・気圧複合センサー",
            ),
        },
    )


class TestSensorContext:
    """Test sensor context building."""

    def test_builds_zone_list(self):
        spatial = _make_spatial_config()
        gen = ReportGenerator.__new__(ReportGenerator)
        gen._spatial = spatial

        ctx = gen._build_sensor_context()
        assert "テストゾーンA" in ctx
        assert "テストゾーンB" in ctx
        assert "20.0m²" in ctx

    def test_includes_device_context(self):
        spatial = _make_spatial_config()
        gen = ReportGenerator.__new__(ReportGenerator)
        gen._spatial = spatial

        ctx = gen._build_sensor_context()
        assert "外気の影響を受けやすい" in ctx
        assert "CO2・温湿度・気圧複合センサー" in ctx

    def test_includes_channels(self):
        spatial = _make_spatial_config()
        gen = ReportGenerator.__new__(ReportGenerator)
        gen._spatial = spatial

        ctx = gen._build_sensor_context()
        assert "temperature" in ctx
        assert "humidity" in ctx
        assert "illuminance" in ctx

    def test_device_without_context(self):
        """Devices without context should still be listed."""
        spatial = _make_spatial_config()
        gen = ReportGenerator.__new__(ReportGenerator)
        gen._spatial = spatial

        ctx = gen._build_sensor_context()
        assert "照度センサー" in ctx


class TestReportParsing:
    """Test report section parsing."""

    def test_parses_standard_sections(self):
        gen = ReportGenerator.__new__(ReportGenerator)
        gen._spatial = _make_spatial_config()

        raw = """### 1. エグゼクティブサマリー
今日は穏やかな一日でした。

### 2. 環境分析
温度は22℃で安定していました。

### 3. 在室・利用分析
ゾーンAが最も利用されました。

### 4. AI行動履歴
認知サイクル100回実行。

### 5. 異常・注意事項
特に異常なし。

### 6. 改善提案
換気の改善を推奨します。"""

        sections = gen._parse_report_sections(raw)
        assert "executive_summary" in sections
        assert "environment_analysis" in sections
        assert "occupancy_analysis" in sections
        assert "ai_activity" in sections
        assert "anomalies" in sections
        assert "recommendations" in sections
        assert "穏やかな" in sections["executive_summary"]
        assert "22℃" in sections["environment_analysis"]

    def test_parses_alternative_headings(self):
        gen = ReportGenerator.__new__(ReportGenerator)
        gen._spatial = _make_spatial_config()

        raw = """## エグゼクティブサマリー
概要です。

## 環境分析
環境データです。

## 在室分析
利用データです。

## 異常
異常データです。

## 提案
提案です。"""

        sections = gen._parse_report_sections(raw)
        assert "executive_summary" in sections
        assert "environment_analysis" in sections
        assert "occupancy_analysis" in sections
        assert "anomalies" in sections
        assert "recommendations" in sections

    def test_preamble_becomes_summary(self):
        gen = ReportGenerator.__new__(ReportGenerator)
        gen._spatial = _make_spatial_config()

        raw = """これは冒頭のテキストです。

### 環境分析
データです。"""

        sections = gen._parse_report_sections(raw)
        assert "executive_summary" in sections
        assert "冒頭のテキスト" in sections["executive_summary"]


class TestDataFormatting:
    """Test period data formatting."""

    def test_formats_hourly_stats(self):
        gen = ReportGenerator.__new__(ReportGenerator)
        gen._spatial = _make_spatial_config()

        data = {
            "hourly_stats": [
                {
                    "hour": "2026-03-26T09:00:00+09:00",
                    "zones": {
                        "zone_a": {
                            "avg_temperature": 22.5,
                            "avg_humidity": 45.0,
                            "avg_co2": 600,
                        },
                    },
                    "tasks_created": 1,
                    "llm_cycles": 10,
                    "total_tool_calls": 5,
                },
            ],
            "llm_activity": {
                "total_cycles": 100,
                "total_tool_calls": 50,
                "avg_cycle_duration_sec": 2.5,
            },
            "occupancy_heatmap": [
                {
                    "zone": "zone_a",
                    "hour": "2026-03-26T09:00:00+09:00",
                    "person_count_avg": 3.5,
                },
            ],
            "events": [
                {
                    "time": "2026-03-26T10:00:00+09:00",
                    "zone": "zone_a",
                    "type": "world_model_co2_threshold",
                    "severity": "warning",
                },
            ],
        }

        result = gen._format_period_data(data, "daily")
        assert "テストゾーンA" in result
        assert "22.5" in result
        assert "100" in result  # LLM cycles
        assert "co2_threshold" in result

    def test_empty_data(self):
        gen = ReportGenerator.__new__(ReportGenerator)
        gen._spatial = _make_spatial_config()

        data = {
            "hourly_stats": [],
            "llm_activity": {},
            "occupancy_heatmap": [],
            "events": [],
        }

        result = gen._format_period_data(data, "daily")
        assert result == "データなし"


class TestPromptBuilding:
    """Test prompt construction."""

    def test_daily_prompt_structure(self):
        gen = ReportGenerator.__new__(ReportGenerator)
        gen._spatial = _make_spatial_config()

        from datetime import datetime, timezone, timedelta
        tz = timezone(timedelta(hours=9))
        start = datetime(2026, 3, 26, 0, 0, tzinfo=tz)
        end = datetime(2026, 3, 27, 0, 0, tzinfo=tz)

        messages = gen._build_report_prompt(
            "daily",
            {"hourly_stats": [], "llm_activity": {}, "occupancy_heatmap": [], "events": []},
            "テストコンテキスト",
            start, end,
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "日次" in messages[0]["content"]
        assert "2026-03-26" in messages[1]["content"]
        assert "テストコンテキスト" in messages[1]["content"]

    def test_weekly_prompt_uses_correct_label(self):
        gen = ReportGenerator.__new__(ReportGenerator)
        gen._spatial = _make_spatial_config()

        from datetime import datetime, timezone, timedelta
        tz = timezone(timedelta(hours=9))
        start = datetime(2026, 3, 23, 0, 0, tzinfo=tz)
        end = datetime(2026, 3, 30, 0, 0, tzinfo=tz)

        messages = gen._build_report_prompt(
            "weekly",
            {"hourly_stats": [], "llm_activity": {}, "occupancy_heatmap": [], "events": []},
            "",
            start, end,
        )
        assert "週次" in messages[0]["content"]
