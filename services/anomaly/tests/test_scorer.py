"""Tests for the anomaly scorer."""
import time

import numpy as np
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from scorer import Scorer, AnomalyResult


@pytest.fixture
def scorer():
    return Scorer(warning_threshold=3.0, critical_threshold=5.0)


class TestSeverityClassification:
    def test_below_threshold(self, scorer):
        assert scorer._classify_severity(2.9) is None

    def test_warning(self, scorer):
        assert scorer._classify_severity(3.0) == "warning"
        assert scorer._classify_severity(4.9) == "warning"

    def test_critical(self, scorer):
        assert scorer._classify_severity(5.0) == "critical"
        assert scorer._classify_severity(10.0) == "critical"

    def test_exact_boundary(self, scorer):
        assert scorer._classify_severity(3.0) == "warning"
        assert scorer._classify_severity(5.0) == "critical"


class TestScoreComputation:
    def test_normal_values(self, scorer):
        predicted = np.array([22.0, 50.0])
        actual = np.array([22.5, 51.0])
        stds = np.array([1.0, 5.0])
        results = scorer.compute_scores(predicted, actual, stds, "zone_01", ["temp", "hum"])
        assert len(results) == 0  # below threshold

    def test_anomaly_detected(self, scorer):
        predicted = np.array([22.0])
        actual = np.array([28.0])  # 6 stds away
        stds = np.array([1.0])
        results = scorer.compute_scores(predicted, actual, stds, "zone_01", ["temp"])
        assert len(results) == 1
        assert results[0].severity == "critical"
        assert results[0].score == 6.0

    def test_warning_level(self, scorer):
        predicted = np.array([22.0])
        actual = np.array([25.5])  # 3.5 stds
        stds = np.array([1.0])
        results = scorer.compute_scores(predicted, actual, stds, "zone_01", ["temp"])
        assert len(results) == 1
        assert results[0].severity == "warning"

    def test_source_field(self, scorer):
        predicted = np.array([0.0])
        actual = np.array([6.0])
        stds = np.array([1.0])
        results = scorer.compute_scores(predicted, actual, stds, "z", ["ch"], source="realtime")
        assert results[0].source == "realtime"


class TestCooldown:
    def test_cooldown_prevents_duplicate(self, scorer):
        predicted = np.array([0.0])
        actual = np.array([6.0])
        stds = np.array([1.0])

        r1 = scorer.compute_scores(predicted, actual, stds, "zone_01", ["temp"])
        assert len(r1) == 1

        r2 = scorer.compute_scores(predicted, actual, stds, "zone_01", ["temp"])
        assert len(r2) == 0  # cooldown active

    def test_different_channels_not_blocked(self, scorer):
        predicted = np.array([0.0])
        actual = np.array([6.0])
        stds = np.array([1.0])

        scorer.compute_scores(predicted, actual, stds, "zone_01", ["temp"])
        r2 = scorer.compute_scores(predicted, actual, stds, "zone_01", ["co2"])
        assert len(r2) == 1  # different channel, no cooldown

    def test_clear_cooldown(self, scorer):
        predicted = np.array([0.0])
        actual = np.array([6.0])
        stds = np.array([1.0])

        scorer.compute_scores(predicted, actual, stds, "zone_01", ["temp"])
        scorer.clear_cooldown("zone_01", "temp")

        r2 = scorer.compute_scores(predicted, actual, stds, "zone_01", ["temp"])
        assert len(r2) == 1

    def test_clear_all_cooldowns(self, scorer):
        predicted = np.array([0.0])
        actual = np.array([6.0])
        stds = np.array([1.0])

        scorer.compute_scores(predicted, actual, stds, "zone_01", ["temp"])
        scorer.clear_cooldown()

        r2 = scorer.compute_scores(predicted, actual, stds, "zone_01", ["temp"])
        assert len(r2) == 1

    def test_zero_std_safe(self, scorer):
        predicted = np.array([0.0])
        actual = np.array([6.0])
        stds = np.array([0.0])  # zero std
        results = scorer.compute_scores(predicted, actual, stds, "zone_01", ["temp"])
        assert len(results) == 1  # uses 1.0 fallback
