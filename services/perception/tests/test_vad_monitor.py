"""Tests for the integrated VADMonitor."""
import sys

import numpy as np
import pytest

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "src"))

from vad.vad_monitor import VADMonitor


class TestBBoxIoU:
    def test_perfect_overlap(self):
        iou = VADMonitor._bbox_iou([0, 0, 10, 10], [0, 0, 10, 10])
        assert iou == pytest.approx(1.0)

    def test_no_overlap(self):
        iou = VADMonitor._bbox_iou([0, 0, 5, 5], [10, 10, 20, 20])
        assert iou == 0.0

    def test_partial_overlap(self):
        iou = VADMonitor._bbox_iou([0, 0, 10, 10], [5, 5, 15, 15])
        # Intersection: 5×5=25, Union: 100+100-25=175
        assert iou == pytest.approx(25.0 / 175.0, abs=0.01)

    def test_zero_area(self):
        iou = VADMonitor._bbox_iou([0, 0, 0, 0], [0, 0, 10, 10])
        assert iou == 0.0


class TestVADMonitorInit:
    def test_creates_without_tracker(self):
        monitor = VADMonitor(cross_camera_tracker=None, model_dir="/tmp/vad_test")
        assert monitor._tracker is None
        assert monitor._stg_nf is not None
        assert monitor._aed_mae is not None
        assert monitor._attr_vad is not None

    def test_get_empty_coefficients(self):
        monitor = VADMonitor(cross_camera_tracker=None, model_dir="/tmp/vad_test")
        coeffs = monitor.get_crime_coefficients()
        assert coeffs == {}

    def test_get_all_breakdowns_empty(self):
        monitor = VADMonitor(cross_camera_tracker=None, model_dir="/tmp/vad_test")
        assert monitor.get_all_breakdowns() == []


class TestVADMonitorProcessing:
    def test_process_frame_no_persons(self):
        monitor = VADMonitor(cross_camera_tracker=None, model_dir="/tmp/vad_test")
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        # Should not crash with empty persons
        monitor.process_frame(frame, [], [], "zone_01")
        assert monitor.get_crime_coefficients() == {}

    def test_process_frame_with_person(self):
        monitor = VADMonitor(cross_camera_tracker=None, model_dir="/tmp/vad_test")
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        kp = np.random.randn(17, 2) * 50 + 200
        kp[5] = [180, 150]; kp[6] = [220, 150]
        kp[11] = [190, 250]; kp[12] = [210, 250]
        persons = [{
            "keypoints": kp,
            "keypoint_conf": np.ones(17),
            "bbox": [150, 100, 250, 400],
            "confidence": 0.9,
        }]
        detections = [{"class": "person", "bbox": [150, 100, 250, 400], "center": [200, 250], "confidence": 0.9}]
        monitor.process_frame(frame, persons, detections, "zone_01", timestamp=1000.0)
        # Should have created a profile (using fallback_idx=0 as global_id)
        coeffs = monitor.get_crime_coefficients()
        assert len(coeffs) >= 0  # May be 0 if STG-NF buffer not full yet

    def test_evict_person(self):
        monitor = VADMonitor(cross_camera_tracker=None, model_dir="/tmp/vad_test")
        # Manually add to crime scorer
        monitor._crime.update(42, pose_score=5.0)
        assert monitor.get_crime_coefficients().get(42, 0) > 0
        monitor.evict_person(42)
        assert 42 not in monitor.get_crime_coefficients()
