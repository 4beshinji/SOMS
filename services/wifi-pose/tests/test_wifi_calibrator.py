"""Unit tests for WifiCalibrator — affine calibration from WiFi↔YOLO pairs."""
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from wifi_calibrator import WifiCalibrator, CalibrationPair


class TestWifiCalibrator:
    """Tests for WifiCalibrator."""

    def setup_method(self):
        # Reset singleton between tests
        WifiCalibrator._instance = None

    def _make_calibrator(self, cache_path=None, min_pairs=5):
        return WifiCalibrator(
            cache_path=cache_path,
            sliding_window_size=200,
            min_pairs=min_pairs,
        )

    def test_add_pair_accumulates(self):
        """Pairs are accumulated in the per-zone sliding window."""
        cal = self._make_calibrator(min_pairs=100)
        for i in range(10):
            cal.add_pair(CalibrationPair(
                wifi_xy=[float(i), float(i)],
                yolo_xy=[float(i) * 2, float(i) * 2],
                timestamp=float(i),
                zone="office",
                confidence=0.9,
            ))
        assert len(cal._pairs["office"]) == 10

    def test_try_calibrate_insufficient_pairs(self):
        """Calibration fails with fewer pairs than min_pairs."""
        cal = self._make_calibrator(min_pairs=20)
        for i in range(5):
            cal.add_pair(CalibrationPair(
                wifi_xy=[float(i), float(i)],
                yolo_xy=[float(i) * 2, float(i) * 2],
                timestamp=float(i),
                zone="office",
                confidence=0.9,
            ))
        result = cal.try_calibrate("office")
        assert result is False
        assert not cal.has_calibration("office")

    def test_try_calibrate_success(self):
        """Calibration succeeds with enough pairs (cv2 mock returns identity)."""
        cal = self._make_calibrator(min_pairs=5)
        for i in range(10):
            cal.add_pair(CalibrationPair(
                wifi_xy=[float(i), float(i)],
                yolo_xy=[float(i) * 2, float(i) * 2],
                timestamp=float(i),
                zone="office",
                confidence=0.9,
            ))
        result = cal.try_calibrate("office")
        assert result is True
        assert cal.has_calibration("office")

    def test_correct_without_calibration(self):
        """correct() passes through uncorrected when no calibration exists."""
        cal = self._make_calibrator()
        result = cal.correct("unknown_zone", [5.0, 3.0])
        assert result == [5.0, 3.0]

    def test_correct_with_calibration(self):
        """correct() applies the affine transform."""
        cal = self._make_calibrator(min_pairs=5)
        # Manually set a known transform (2x scale)
        cal._transforms["office"] = np.array(
            [[2.0, 0.0, 1.0], [0.0, 2.0, -1.0]], dtype=np.float64
        )
        result = cal.correct("office", [3.0, 4.0])
        # Expected: [2*3+1, 2*4-1] = [7.0, 7.0]
        assert len(result) == 2
        assert abs(result[0] - 7.0) < 0.01
        assert abs(result[1] - 7.0) < 0.01

    def test_save_and_load_cache(self):
        """Cache round-trips through JSON correctly."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            cache_path = f.name

        try:
            cal = self._make_calibrator(cache_path=cache_path)
            cal._transforms["office"] = np.array(
                [[1.5, 0.1, 2.0], [0.2, 1.5, 3.0]], dtype=np.float64
            )
            cal._save_cache()

            # Load in new instance
            cal2 = WifiCalibrator(cache_path=cache_path)
            assert cal2.has_calibration("office")
            assert np.allclose(cal2._transforms["office"], cal._transforms["office"])
        finally:
            Path(cache_path).unlink(missing_ok=True)

    def test_get_calibrated_zones(self):
        """get_calibrated_zones returns zones with transforms."""
        cal = self._make_calibrator()
        assert cal.get_calibrated_zones() == []
        cal._transforms["zone_a"] = np.eye(2, 3)
        cal._transforms["zone_b"] = np.eye(2, 3)
        assert sorted(cal.get_calibrated_zones()) == ["zone_a", "zone_b"]

    def test_sliding_window_evicts_old(self):
        """Sliding window evicts old pairs when maxlen is exceeded."""
        cal = WifiCalibrator(sliding_window_size=5, min_pairs=100)
        for i in range(10):
            cal.add_pair(CalibrationPair(
                wifi_xy=[float(i), 0.0],
                yolo_xy=[0.0, float(i)],
                timestamp=float(i),
                zone="z",
                confidence=1.0,
            ))
        assert len(cal._pairs["z"]) == 5
        assert cal._pairs["z"][0].wifi_xy == [5.0, 0.0]
