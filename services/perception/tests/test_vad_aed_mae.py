"""Tests for AED-MAE frame anomaly detector."""
import sys

import numpy as np
import pytest

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "src"))

from vad.aed_mae import AEDMAEDetector


class TestRunningStats:
    def test_initial_state(self):
        detector = AEDMAEDetector()
        assert detector._running_stats["count"] == 0

    def test_welford_update(self):
        detector = AEDMAEDetector()
        # Simulate stats updates
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        for v in values:
            detector._update_stats(v)

        assert detector._running_stats["count"] == 5
        assert abs(detector._running_stats["mean"] - 3.0) < 0.01
        # Variance of [1,2,3,4,5] = 2.0 (population)
        assert abs(detector._running_stats["var"] - 2.0) < 0.1


class TestAEDMAEDetector:
    def test_score_none_without_model(self):
        """With mocked torch, model is None → score_frame returns None."""
        detector = AEDMAEDetector()
        # With mocked torch, model creation fails gracefully
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        result = detector.score_frame(frame)
        assert result is None  # No model → None

    def test_detector_creation(self):
        detector = AEDMAEDetector(img_size=32)
        assert detector._img_size == 32
        assert detector._n_augments == 4
        # Model is None due to mocked torch
        assert detector._model is None
