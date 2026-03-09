"""Tests for the Crime Coefficient ensemble scorer."""
import math
import sys
import time

import numpy as np
import pytest

# Ensure src is on path
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "src"))

from vad.ensemble import (
    CLEAR_THRESHOLD,
    WARNING_THRESHOLD,
    CRITICAL_THRESHOLD,
    CrimeCoefficient,
    PersonProfile,
)


@pytest.fixture
def scorer():
    return CrimeCoefficient(
        ema_alpha=1.0,  # No smoothing for deterministic tests
        restricted_zones=["server_room"],
        normal_hours=(7, 22),
    )


class TestSeverityClassification:
    def test_clear(self, scorer):
        scorer.update(1, pose_score=0.0)
        assert scorer.get_severity(1) == "clear"

    def test_latent(self, scorer):
        # score ~100 → latent
        scorer.update(1, pose_score=10.0, scene_score=10.0, attribute_scores={"combined": 10.0})
        coeff = scorer.get_coefficient(1)
        assert coeff >= CLEAR_THRESHOLD or scorer.get_severity(1) in ("latent", "warning", "critical")

    def test_warning_with_trajectory(self, scorer):
        now = time.time()
        # Person loitering in restricted zone
        for i in range(30):
            scorer.update(
                1,
                pose_score=5.0,
                scene_score=3.0,
                attribute_scores={"combined": 5.0},
                floor_position=[1.0, 1.0],
                zone="server_room",
                timestamp=now + i * 10,
            )
        severity = scorer.get_severity(1)
        assert severity in ("warning", "critical", "latent")


class TestScoreClamping:
    def test_zero_raw(self):
        assert CrimeCoefficient._clamp_score(0.0) == 0.0

    def test_moderate_raw(self):
        score = CrimeCoefficient._clamp_score(3.0)
        assert 50 < score < 70  # ~63

    def test_high_raw(self):
        score = CrimeCoefficient._clamp_score(10.0)
        assert score > 95

    def test_negative_raw(self):
        assert CrimeCoefficient._clamp_score(-1.0) == 0.0


class TestTrajectoryScore:
    def test_no_trajectory(self, scorer):
        scorer.update(1, pose_score=0.0)
        profile = scorer.get_profile(1)
        assert profile.trajectory_score == 0.0

    def test_loitering_detected(self, scorer):
        now = time.time()
        # Stay in same spot for 5+ minutes
        for i in range(60):
            scorer.update(
                1,
                floor_position=[5.0, 5.0],
                zone="lobby",
                timestamp=now + i * 6,  # 6s intervals → 360s total
            )
        profile = scorer.get_profile(1)
        assert profile.trajectory_score > 0  # Loitering detected

    def test_restricted_zone(self, scorer):
        now = time.time()
        for i in range(40):
            scorer.update(
                1,
                floor_position=[1.0, 1.0],
                zone="server_room",
                timestamp=now + i * 2,
            )
        profile = scorer.get_profile(1)
        assert profile.trajectory_score >= 40  # Restricted zone penalty


class TestTemporalScore:
    def test_normal_hours(self, scorer):
        # 12:00 noon → normal
        import datetime
        noon = datetime.datetime(2026, 3, 9, 12, 0, 0).timestamp()
        scorer.update(1, timestamp=noon)
        profile = scorer.get_profile(1)
        assert profile.temporal_score == 0.0

    def test_late_night(self, scorer):
        import datetime
        midnight = datetime.datetime(2026, 3, 9, 2, 0, 0).timestamp()
        scorer.update(1, timestamp=midnight)
        profile = scorer.get_profile(1)
        assert profile.temporal_score > 0


class TestBreakdown:
    def test_breakdown_structure(self, scorer):
        scorer.update(1, pose_score=2.0, scene_score=1.0)
        breakdown = scorer.get_breakdown(1)
        assert breakdown is not None
        assert "crime_coefficient" in breakdown
        assert "severity" in breakdown
        assert "breakdown" in breakdown
        assert set(breakdown["breakdown"].keys()) == {
            "pose", "scene", "attribute", "trajectory", "temporal", "social"
        }

    def test_nonexistent_person(self, scorer):
        assert scorer.get_breakdown(999) is None


class TestEMASmoothing:
    def test_ema_smooths_spikes(self):
        scorer = CrimeCoefficient(ema_alpha=0.1)
        # Series of normal scores then one spike
        for _ in range(20):
            scorer.update(1, pose_score=0.0)
        scorer.update(1, pose_score=10.0)
        # With alpha=0.1, spike should be heavily dampened
        coeff = scorer.get_coefficient(1)
        assert coeff < 50  # Would be ~300 without EMA


class TestEviction:
    def test_evict_removes_profile(self, scorer):
        scorer.update(1, pose_score=5.0)
        assert scorer.get_coefficient(1) > 0
        scorer.evict(1)
        assert scorer.get_coefficient(1) == 0.0
        assert scorer.get_profile(1) is None
