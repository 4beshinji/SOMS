"""Tests for AI-VAD attribute-based anomaly detector."""
import sys

import numpy as np
import pytest

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "src"))

from vad.attribute_vad import AttributeVADDetector, GaussianDensity


class TestGaussianDensity:
    def test_unfitted_returns_zero(self):
        gd = GaussianDensity(3)
        assert gd.score(np.array([1, 2, 3])) == 0.0

    def test_fit_and_score_normal(self):
        gd = GaussianDensity(2)
        data = np.random.randn(100, 2) * 2 + 5
        gd.fit(data)
        # Score at mean should be ~0
        score_at_mean = gd.score(gd.mean)
        assert score_at_mean < 0.5

    def test_outlier_high_score(self):
        gd = GaussianDensity(2)
        data = np.random.randn(100, 2)
        gd.fit(data)
        # Far outlier
        score = gd.score(np.array([10.0, 10.0]))
        assert score > 5.0

    def test_save_load_roundtrip(self):
        gd = GaussianDensity(3)
        data = np.random.randn(50, 3)
        gd.fit(data)
        saved = gd.save()

        gd2 = GaussianDensity(3)
        gd2.load(saved)
        assert gd2._fitted
        np.testing.assert_array_almost_equal(gd.mean, gd2.mean)


class TestAttributeExtraction:
    def test_extract_basic(self):
        detector = AttributeVADDetector()
        attrs = detector.extract_attributes(
            person_id=1,
            bbox=[100, 100, 200, 400],
            keypoints=np.random.randn(17, 2) * 50 + 150,
            confidences=np.ones(17),
            frame=None,
            timestamp=1000.0,
        )
        assert attrs is not None
        assert attrs.person_id == 1
        assert len(attrs.velocity) == 3  # speed, dx_norm, dy_norm
        assert len(attrs.pose_features) == 34

    def test_velocity_computation(self):
        detector = AttributeVADDetector()
        kp = np.random.randn(17, 2) * 50 + 150
        kp[11] = [140, 300]; kp[12] = [160, 300]
        conf = np.ones(17)

        # First call: no velocity yet
        attrs1 = detector.extract_attributes(
            1, [100, 100, 200, 400], kp, conf, None, 1000.0
        )
        assert attrs1.speed == 0.0

        # Second call: 1 second later, moved 10 pixels
        attrs2 = detector.extract_attributes(
            1, [110, 100, 210, 400], kp, conf, None, 1001.0
        )
        assert attrs2.speed == pytest.approx(10.0, abs=0.1)

    def test_score_unfitted(self):
        detector = AttributeVADDetector()
        kp = np.random.randn(17, 2) * 50 + 150
        kp[11] = [140, 300]; kp[12] = [160, 300]
        conf = np.ones(17)
        attrs = detector.extract_attributes(
            1, [100, 100, 200, 400], kp, conf, None, 1000.0
        )
        scores = detector.score(attrs)
        assert "combined" in scores
        assert scores["combined"] == 0.0  # Unfitted densities return 0

    def test_evict(self):
        detector = AttributeVADDetector()
        kp = np.random.randn(17, 2) * 50 + 150
        conf = np.ones(17)
        detector.extract_attributes(1, [100, 100, 200, 400], kp, conf, None, 1000.0)
        assert 1 in detector._prev_positions
        detector.evict(1)
        assert 1 not in detector._prev_positions


class TestAttributeScoring:
    def test_fitted_scores(self):
        detector = AttributeVADDetector()

        # Fit on normal data
        normal_vel = np.random.randn(100, 3) * 0.5
        normal_pose = np.random.randn(100, 34) * 0.3
        detector._velocity_density.fit(normal_vel)
        detector._pose_density.fit(normal_pose)

        # Score a normal sample
        kp = np.random.randn(17, 2) * 50 + 150
        kp[11] = [140, 300]; kp[12] = [160, 300]
        conf = np.ones(17)
        attrs = detector.extract_attributes(
            1, [100, 100, 200, 400], kp, conf, None, 1000.0
        )
        scores = detector.score(attrs)
        assert scores["velocity"] >= 0
        assert scores["pose"] >= 0
