"""Unit tests for tracking.aruco_calibrator — ArUco marker calibration."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# conftest.py pre-installs cv2 mock into sys.modules, so this import works.
from tracking.aruco_calibrator import ArucoCalibrator


# ── Helpers ──────────────────────────────────────────────────────


def _get_cv2_mock():
    """Return the cv2 MagicMock that was installed by conftest."""
    return sys.modules["cv2"]


def _make_calibrator(world_markers=None, cache_path=None):
    """Create a fresh ArucoCalibrator instance for testing.

    Resets the singleton and configures the cv2 mock's ArUco API.
    """
    ArucoCalibrator._instance = None

    if world_markers is None:
        world_markers = {
            "0": {"corners": [[0, 0], [0.2, 0], [0.2, 0.2], [0, 0.2]]},
            "1": {"corners": [[1, 0], [1.2, 0], [1.2, 0.2], [1, 0.2]]},
            "2": {"corners": [[0, 1], [0.2, 1], [0.2, 1.2], [0, 1.2]]},
            "3": {"corners": [[1, 1], [1.2, 1], [1.2, 1.2], [1, 1.2]]},
        }

    calibrator = ArucoCalibrator(
        aruco_markers=world_markers,
        aruco_dict_name="DICT_4X4_50",
        cache_path=cache_path,
    )

    # The detector is created during __init__ via cv2.aruco.ArucoDetector(...)
    # It is stored as self._detector.  We return it for test setup convenience.
    detector = calibrator._detector

    return calibrator, detector


# ── Tests ────────────────────────────────────────────────────────


class TestArucoCalibrator:
    """Tests for the ArucoCalibrator class."""

    def setup_method(self):
        """Reset singleton before each test."""
        ArucoCalibrator._instance = None

    def test_init_stores_world_markers(self):
        """Constructor stores world marker configurations."""
        markers = {
            "0": {"corners": [[0, 0], [1, 0], [1, 1], [0, 1]]},
        }
        calibrator, _ = _make_calibrator(world_markers=markers)
        assert calibrator._world_markers == markers

    def test_has_calibration_false_initially(self):
        """No camera is calibrated initially."""
        calibrator, _ = _make_calibrator()
        assert calibrator.has_calibration("cam_01") is False

    def test_get_calibrated_cameras_empty_initially(self):
        """No calibrated cameras initially."""
        calibrator, _ = _make_calibrator()
        assert calibrator.get_calibrated_cameras() == []

    def test_calibrate_camera_insufficient_markers(self):
        """Calibration fails when fewer markers than min_markers are detected."""
        calibrator, detector = _make_calibrator()

        # Only 2 markers detected (need 4)
        ids = np.array([[0], [1]])
        corners = [
            np.array([[[10, 10], [50, 10], [50, 50], [10, 50]]], dtype=np.float32),
            np.array([[[100, 10], [140, 10], [140, 50], [100, 50]]], dtype=np.float32),
        ]
        detector.detectMarkers.return_value = (corners, ids, None)

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = calibrator.calibrate_camera("cam_01", image, min_markers=4)

        assert result["status"] == "failed"
        assert result["camera_id"] == "cam_01"
        assert result["markers_detected"] == 2
        assert "Insufficient markers" in result["error"]

    def test_calibrate_camera_no_markers_detected(self):
        """Calibration fails when no markers are detected (ids is None)."""
        calibrator, detector = _make_calibrator()

        detector.detectMarkers.return_value = ([], None, None)

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = calibrator.calibrate_camera("cam_01", image)

        assert result["status"] == "failed"
        assert result["markers_detected"] == 0

    def test_calibrate_camera_success(self):
        """Successful calibration when enough known markers are found."""
        calibrator, detector = _make_calibrator()
        mock_cv2 = _get_cv2_mock()

        # 4 markers detected, all known
        ids = np.array([[0], [1], [2], [3]])
        corners = []
        for i in range(4):
            c = np.array([[[i*100+10, 10], [i*100+50, 10],
                           [i*100+50, 50], [i*100+10, 50]]], dtype=np.float32)
            corners.append(c)
        detector.detectMarkers.return_value = (corners, ids, None)

        # Mock findHomography to return a valid 3x3 matrix
        H = np.eye(3, dtype=np.float64)
        mask = np.ones((16, 1), dtype=np.uint8)
        mock_cv2.findHomography.return_value = (H, mask)

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = calibrator.calibrate_camera("cam_01", image, min_markers=4)

        assert result["status"] == "ok"
        assert result["camera_id"] == "cam_01"
        assert result["markers_detected"] == 4
        assert result["inlier_points"] == 16
        assert result["total_points"] == 16
        assert calibrator.has_calibration("cam_01") is True

    def test_calibrate_camera_homography_fails(self):
        """Calibration fails when findHomography returns None."""
        calibrator, detector = _make_calibrator()
        mock_cv2 = _get_cv2_mock()

        ids = np.array([[0], [1], [2], [3]])
        corners = []
        for i in range(4):
            c = np.array([[[i*100+10, 10], [i*100+50, 10],
                           [i*100+50, 50], [i*100+10, 50]]], dtype=np.float32)
            corners.append(c)
        detector.detectMarkers.return_value = (corners, ids, None)

        # findHomography returns None
        mock_cv2.findHomography.return_value = (None, None)

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = calibrator.calibrate_camera("cam_01", image, min_markers=4)

        assert result["status"] == "failed"
        assert "Homography computation failed" in result["error"]

    def test_calibrate_camera_unknown_markers_filtered(self):
        """Markers not in world_markers are ignored during calibration."""
        # Only define marker IDs 0 and 1 as known
        markers = {
            "0": {"corners": [[0, 0], [0.2, 0], [0.2, 0.2], [0, 0.2]]},
            "1": {"corners": [[1, 0], [1.2, 0], [1.2, 0.2], [1, 0.2]]},
        }
        calibrator, detector = _make_calibrator(world_markers=markers)

        # Detect 4 markers but only 2 are known
        ids = np.array([[0], [1], [99], [100]])
        corners = []
        for i in range(4):
            c = np.array([[[i*100+10, 10], [i*100+50, 10],
                           [i*100+50, 50], [i*100+10, 50]]], dtype=np.float32)
            corners.append(c)
        detector.detectMarkers.return_value = (corners, ids, None)

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        # Need 4 markers matched, but only 2 are known
        result = calibrator.calibrate_camera("cam_01", image, min_markers=4)

        assert result["status"] == "failed"
        assert "Not enough known markers" in result["error"]

    def test_project_to_floor_not_calibrated(self):
        """project_to_floor returns None for uncalibrated camera."""
        calibrator, _ = _make_calibrator()
        result = calibrator.project_to_floor("cam_01", [100.0, 200.0])
        assert result is None

    def test_project_to_floor_after_calibration(self):
        """project_to_floor transforms pixel coordinates using homography."""
        calibrator, _ = _make_calibrator()
        mock_cv2 = _get_cv2_mock()

        # Inject a pre-computed homography
        H = np.eye(3, dtype=np.float64)
        calibrator._homographies["cam_01"] = H

        # Mock perspectiveTransform to return a known result
        expected_result = np.array([[[2.5, 3.5]]], dtype=np.float64)
        mock_cv2.perspectiveTransform.return_value = expected_result

        result = calibrator.project_to_floor("cam_01", [100.0, 200.0])

        assert result is not None
        assert len(result) == 2
        assert result[0] == pytest.approx(2.5)
        assert result[1] == pytest.approx(3.5)

    def test_cache_save_and_load(self):
        """Homographies can be saved to and loaded from JSON cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = str(Path(tmpdir) / "calibration_cache.json")

            # Create calibrator and inject a homography
            calibrator, _ = _make_calibrator(cache_path=cache_file)
            H = np.array([[1.0, 0.0, 10.0],
                          [0.0, 1.0, 20.0],
                          [0.0, 0.0, 1.0]], dtype=np.float64)
            calibrator._homographies["cam_01"] = H
            calibrator._save_cache()

            # Verify the file was written
            assert Path(cache_file).exists()
            data = json.loads(Path(cache_file).read_text())
            assert "cam_01" in data

            # Create a new calibrator and load the cache
            calibrator2, _ = _make_calibrator(cache_path=cache_file)
            calibrator2._load_cache()

            assert calibrator2.has_calibration("cam_01")
            loaded_H = calibrator2._homographies["cam_01"]
            assert np.allclose(loaded_H, H)

    def test_cache_load_missing_file(self):
        """_load_cache handles missing cache file gracefully."""
        calibrator, _ = _make_calibrator(
            cache_path="/tmp/nonexistent_calibration_cache_12345.json"
        )
        # Should not raise
        calibrator._load_cache()
        assert calibrator.get_calibrated_cameras() == []

    def test_get_calibrated_cameras_after_calibration(self):
        """get_calibrated_cameras returns all cameras with homographies."""
        calibrator, _ = _make_calibrator()
        calibrator._homographies["cam_01"] = np.eye(3)
        calibrator._homographies["cam_02"] = np.eye(3)

        cameras = calibrator.get_calibrated_cameras()
        assert sorted(cameras) == ["cam_01", "cam_02"]

    def test_singleton_pattern(self):
        """get_instance returns the same object on repeated calls."""
        ArucoCalibrator._instance = None

        inst1 = ArucoCalibrator.get_instance(
            aruco_markers={"0": {"corners": [[0,0],[1,0],[1,1],[0,1]]}}
        )
        inst2 = ArucoCalibrator.get_instance()
        assert inst1 is inst2

        # Clean up
        ArucoCalibrator._instance = None

    def test_calibrate_camera_stores_homography(self):
        """After successful calibration, homography is stored internally."""
        calibrator, detector = _make_calibrator()
        mock_cv2 = _get_cv2_mock()

        ids = np.array([[0], [1], [2], [3]])
        corners = []
        for i in range(4):
            c = np.array([[[i*100+10, 10], [i*100+50, 10],
                           [i*100+50, 50], [i*100+10, 50]]], dtype=np.float32)
            corners.append(c)
        detector.detectMarkers.return_value = (corners, ids, None)

        H = np.array([[2.0, 0.0, 5.0],
                       [0.0, 2.0, 10.0],
                       [0.0, 0.0, 1.0]], dtype=np.float64)
        mask = np.ones((16, 1), dtype=np.uint8)
        mock_cv2.findHomography.return_value = (H, mask)

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        calibrator.calibrate_camera("cam_test", image, min_markers=4)

        assert calibrator.has_calibration("cam_test")
        assert np.allclose(calibrator._homographies["cam_test"], H)
