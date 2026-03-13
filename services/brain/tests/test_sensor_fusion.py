"""Unit tests for brain sensor_fusion — weighted sensor aggregation."""
import math
import time
from unittest.mock import patch

import pytest

from world_model.sensor_fusion import SensorFusion


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def fusion():
    return SensorFusion()


# ── Half-life lookup ──────────────────────────────────────────────


class TestHalfLife:
    """Half-life configuration per sensor type."""

    def test_unknown_sensor_gets_default(self, fusion):
        assert fusion._get_half_life("vibration") == fusion.HALF_LIFE["default"]


# ── Reliability scores ────────────────────────────────────────────


class TestReliability:
    """Setting and retrieving reliability scores."""

    def test_default_reliability(self, fusion):
        assert fusion.sensor_reliability["default"] == 0.5

    @pytest.mark.parametrize("value", [0.9, 0.0, 1.0])
    def test_set_reliability(self, fusion, value):
        fusion.set_reliability("sensor_a", value)
        assert fusion.sensor_reliability["sensor_a"] == value

    def test_set_reliability_below_zero_raises(self, fusion):
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            fusion.set_reliability("sensor_a", -0.1)

    def test_set_reliability_above_one_raises(self, fusion):
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            fusion.set_reliability("sensor_a", 1.1)


# ── fuse_temperature / fuse_generic ───────────────────────────────


class TestFuseTemperature:
    """Weighted temperature fusion with age decay."""

    def test_empty_readings_returns_none(self, fusion):
        assert fusion.fuse_temperature([]) is None

    def test_single_recent_reading(self, fusion):
        now = time.time()
        result = fusion.fuse_temperature([("s1", 25.0, now)])
        assert result is not None
        assert abs(result - 25.0) < 0.5

    def test_two_equal_reliability_recent_readings(self, fusion):
        """Two readings of the same age and reliability -> average."""
        now = time.time()
        result = fusion.fuse_temperature([
            ("s1", 20.0, now),
            ("s2", 30.0, now),
        ])
        assert result is not None
        assert abs(result - 25.0) < 0.5

    def test_higher_reliability_sensor_has_more_weight(self, fusion):
        """Sensor with higher reliability pulls the result closer to its value."""
        now = time.time()
        fusion.set_reliability("s_reliable", 1.0)
        fusion.set_reliability("s_weak", 0.1)
        result = fusion.fuse_temperature([
            ("s_reliable", 20.0, now),
            ("s_weak", 30.0, now),
        ])
        assert result is not None
        # Should be closer to 20 than to 30
        assert result < 22.0

    def test_older_reading_has_less_weight(self, fusion):
        """A recent reading dominates over an old one."""
        now = time.time()
        result = fusion.fuse_temperature([
            ("s1", 30.0, now - 600),   # 10 minutes old
            ("s2", 20.0, now),          # fresh
        ])
        assert result is not None
        # Fresh reading (20.0) should dominate
        assert result < 25.0

    def test_fuse_generic_delegates_to_fuse_temperature(self, fusion):
        """fuse_generic uses the same logic."""
        now = time.time()
        readings = [("s1", 50.0, now)]
        temp_result = fusion.fuse_temperature(readings, sensor_type="humidity")
        generic_result = fusion.fuse_generic(readings, sensor_type="humidity")
        assert temp_result == generic_result

    def test_zero_total_weight_returns_none(self, fusion):
        """All sensors with 0 reliability -> total weight 0 -> None."""
        now = time.time()
        fusion.set_reliability("s1", 0.0)
        result = fusion.fuse_temperature([("s1", 25.0, now)])
        # Reliability 0 -> weight 0 -> None
        assert result is None


# ── integrate_occupancy ───────────────────────────────────────────


class TestIntegrateOccupancy:
    """Occupancy integration from vision + PIR."""

    def test_vision_count_only(self, fusion):
        result = fusion.integrate_occupancy(vision_count=3, pir_active=False)
        assert result == 3

    def test_pir_active_vision_zero(self, fusion):
        """PIR active but vision sees nobody -> 1 person estimated."""
        result = fusion.integrate_occupancy(vision_count=0, pir_active=True)
        assert result == 1

    def test_pir_active_vision_nonzero(self, fusion):
        """PIR + vision both active -> use vision count (standard zone)."""
        result = fusion.integrate_occupancy(vision_count=2, pir_active=True)
        assert result == 2

    def test_large_zone_scaling(self, fusion):
        """Zone > 50 m^2 scales vision count by 1.2x."""
        result = fusion.integrate_occupancy(vision_count=5, pir_active=False, zone_size=60.0)
        assert result == 6  # int(5 * 1.2) = 6

    def test_large_zone_no_people(self, fusion):
        """Large zone with 0 vision count -> no scaling."""
        result = fusion.integrate_occupancy(vision_count=0, pir_active=False, zone_size=100.0)
        assert result == 0

    def test_small_zone_no_scaling(self, fusion):
        """Zone <= 50 m^2 does not scale."""
        result = fusion.integrate_occupancy(vision_count=5, pir_active=False, zone_size=50.0)
        assert result == 5

    def test_pir_active_large_zone_zero_vision(self, fusion):
        """PIR active in large zone with zero vision -> 1 person (PIR rule applies first)."""
        result = fusion.integrate_occupancy(vision_count=0, pir_active=True, zone_size=100.0)
        # PIR sets estimated_count to 1; then zone_size > 50 AND vision_count (0) > 0 is False
        # So scaling does not apply. Result = 1.
        assert result == 1
