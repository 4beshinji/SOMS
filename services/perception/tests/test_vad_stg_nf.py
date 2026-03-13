"""Tests for STG-NF pose anomaly detector."""
import sys

import numpy as np
import pytest

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "src"))

from vad.stg_nf import STGNFDetector, _build_adjacency


class TestAdjacencyMatrix:
    def test_shape(self):
        A = _build_adjacency(17)
        assert A.shape == (17, 17)

    def test_symmetric(self):
        A = _build_adjacency(17)
        np.testing.assert_array_almost_equal(A, A.T)

    def test_self_loops(self):
        A = _build_adjacency(17)
        # After normalization, diagonal should be > 0
        assert all(A[i, i] > 0 for i in range(17))


class TestPoseNormalization:
    def test_valid_pose(self):
        kp = np.zeros((17, 2))
        conf = np.ones(17)
        # Set hip midpoint at (100, 200), shoulders at (80, 150) and (120, 150)
        kp[11] = [90, 200]   # L_HIP
        kp[12] = [110, 200]  # R_HIP
        kp[5] = [80, 150]    # L_SHOULDER
        kp[6] = [120, 150]   # R_SHOULDER
        kp[0] = [100, 100]   # NOSE

        result = STGNFDetector._normalize_pose(kp, conf)
        assert result is not None
        assert result.shape == (17, 2)
        # Hip center should be at (0, 0)
        hip_mid_norm = (result[11] + result[12]) / 2
        np.testing.assert_array_almost_equal(hip_mid_norm, [0, 0], decimal=1)

    def test_low_confidence_rejected(self):
        kp = np.zeros((17, 2))
        conf = np.zeros(17)  # All low confidence
        result = STGNFDetector._normalize_pose(kp, conf)
        assert result is None

    def test_zero_torso_length(self):
        kp = np.zeros((17, 2))
        conf = np.ones(17)
        # All keypoints at same position
        kp[:] = [100, 100]
        result = STGNFDetector._normalize_pose(kp, conf)
        assert result is None


class TestSTGNFDetector:
    def test_buffer_fills(self):
        detector = STGNFDetector(seq_len=5)
        kp = np.random.randn(17, 2) * 50 + 100
        conf = np.ones(17)
        # Set proper hip/shoulder positions
        kp[5] = [80, 150]
        kp[6] = [120, 150]
        kp[11] = [90, 200]
        kp[12] = [110, 200]

        for i in range(4):
            result = detector.update(1, kp, conf)
            assert result is None  # Buffer not yet full

    def test_evict(self):
        detector = STGNFDetector(seq_len=3)
        # Manually add buffer entry (bypassing model check)
        from collections import deque
        detector._buffers[1] = deque(maxlen=3)
        detector._buffers[1].append(np.zeros((17, 2)))
        assert 1 in detector._buffers
        detector.evict(1)
        assert 1 not in detector._buffers

    def test_update_returns_none_without_model(self):
        """With mocked torch, model is None → update returns None."""
        detector = STGNFDetector(seq_len=3)
        kp = np.random.randn(17, 2) * 50 + 100
        kp[5] = [80, 150]; kp[6] = [120, 150]
        kp[11] = [90, 200]; kp[12] = [110, 200]
        conf = np.ones(17)
        result = detector.update(1, kp, conf)
        assert result is None
