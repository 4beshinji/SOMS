"""Unit tests for RuleEngine."""
import time
from unittest.mock import MagicMock, patch

import pytest

from conftest import make_zone_state

import os
os.environ.setdefault("GPU_TYPE", "none")

from rule_engine import RuleEngine


def _make_world_model(zones_dict):
    """Create a mock WorldModel with .zones attribute."""
    wm = MagicMock()
    wm.zones = zones_dict
    return wm


def _zone(zone_id="zone_a", display_name="テストゾーン", **kwargs):
    """Create a zone state with metadata.display_name set."""
    zone = make_zone_state(zone_id=zone_id, **kwargs)
    zone.metadata.display_name = display_name
    return zone


class TestEvaluateCritical:
    """Test safety-critical rules."""

    def test_critical_co2(self):
        engine = RuleEngine()
        zone = _zone(co2=1600)
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate_critical(wm)
        assert len(actions) == 1
        assert actions[0]["tool"] == "create_task"
        assert "CO2危険" in actions[0]["args"]["title"]
        assert actions[0]["args"]["urgency"] == 3

    def test_critical_high_temp(self):
        engine = RuleEngine()
        zone = _zone(temperature=38.0)
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate_critical(wm)
        assert len(actions) == 1
        assert "高温警報" in actions[0]["args"]["title"]

    def test_critical_low_temp(self):
        engine = RuleEngine()
        zone = _zone(temperature=5.0)
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate_critical(wm)
        assert len(actions) == 1
        assert "低温警報" in actions[0]["args"]["title"]

    def test_no_critical_in_normal_range(self):
        engine = RuleEngine()
        zone = _zone(temperature=22.0, co2=800, humidity=50)
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate_critical(wm)
        assert len(actions) == 0

    def test_water_leak(self):
        engine = RuleEngine()
        zone = _zone()
        zone.extra_sensors = {"water_leak": 1.0}
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate_critical(wm)
        assert len(actions) == 1
        assert "漏水検知" in actions[0]["args"]["title"]


class TestEvaluateNormal:
    """Test normal threshold rules."""

    def test_high_co2(self):
        engine = RuleEngine()
        zone = _zone(co2=1200)
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate(wm)
        assert len(actions) == 1
        assert "換気推奨" in actions[0]["args"]["title"]

    def test_high_temperature(self):
        engine = RuleEngine()
        zone = _zone(temperature=28.0)
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate(wm)
        assert len(actions) == 1
        assert "室温高め" in actions[0]["args"]["title"]

    def test_low_temperature(self):
        engine = RuleEngine()
        zone = _zone(temperature=15.0)
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate(wm)
        assert len(actions) == 1
        assert "室温低め" in actions[0]["args"]["title"]

    def test_high_humidity(self):
        engine = RuleEngine()
        zone = _zone(humidity=75)
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate(wm)
        assert len(actions) == 1
        assert "湿度高" in actions[0]["args"]["title"]

    def test_low_humidity(self):
        engine = RuleEngine()
        zone = _zone(humidity=20)
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate(wm)
        assert len(actions) == 1
        assert "湿度低" in actions[0]["args"]["title"]

    def test_no_action_in_normal_range(self):
        engine = RuleEngine()
        zone = _zone(temperature=22.0, co2=600, humidity=45)
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate(wm)
        assert len(actions) == 0

    def test_none_values_handled(self):
        """Sensors with None readings should not trigger rules."""
        engine = RuleEngine()
        zone = _zone(temperature=None, co2=None, humidity=None)
        wm = _make_world_model({"zone_a": zone})

        actions = engine.evaluate(wm)
        assert len(actions) == 0


class TestCooldown:
    """Test cooldown mechanism."""

    def test_cooldown_prevents_rapid_fire(self):
        engine = RuleEngine()
        zone = _zone(co2=1200)
        wm = _make_world_model({"zone_a": zone})

        # First call: should trigger
        actions1 = engine.evaluate(wm)
        assert len(actions1) == 1

        # Second call immediately: should be blocked by cooldown
        actions2 = engine.evaluate(wm)
        assert len(actions2) == 0

    def test_cooldown_expires(self):
        engine = RuleEngine()
        zone = _zone(co2=1200)
        wm = _make_world_model({"zone_a": zone})

        # First call
        engine.evaluate(wm)

        # Expire the cooldown
        for key in engine._cooldowns:
            engine._cooldowns[key] = time.time() - 301

        # Should trigger again
        actions = engine.evaluate(wm)
        assert len(actions) == 1


class TestMultipleZones:
    """Test with multiple zones."""

    def test_independent_zone_actions(self):
        engine = RuleEngine()
        zone_a = _zone(zone_id="zone_a", co2=1200)
        zone_b = _zone(zone_id="zone_b", temperature=28.0)
        wm = _make_world_model({"zone_a": zone_a, "zone_b": zone_b})

        actions = engine.evaluate(wm)
        assert len(actions) == 2

    def test_critical_overrides_normal(self):
        """Critical CO2 should fire in critical, not in normal evaluate."""
        engine = RuleEngine()
        zone = _zone(co2=1600)
        wm = _make_world_model({"zone_a": zone})

        critical = engine.evaluate_critical(wm)
        normal = engine.evaluate(wm)

        # Critical should fire
        assert len(critical) == 1
        # Normal should not fire (CO2 > CO2_CRITICAL, not in normal range)
        assert len(normal) == 0


class TestGPUDetection:
    """Test GPU utilization check."""

    def test_no_gpu_returns_false(self):
        engine = RuleEngine()
        assert not engine.should_use_rules()

    @patch("rule_engine.GPU_TYPE", "amd")
    @patch("rule_engine._get_gpu_utilization", return_value=90.0)
    def test_high_gpu_returns_true(self, mock_gpu):
        engine = RuleEngine()
        assert engine.should_use_rules()

    @patch("rule_engine.GPU_TYPE", "amd")
    @patch("rule_engine._get_gpu_utilization", return_value=50.0)
    def test_low_gpu_returns_false(self, mock_gpu):
        engine = RuleEngine()
        assert not engine.should_use_rules()
