"""Unit tests for CalibrationBridge — YOLO↔WiFi matching logic."""
import json
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from calibration_bridge import CalibrationBridge, _PoseRecord
from wifi_calibrator import WifiCalibrator, CalibrationPair


class TestCalibrationBridge:
    """Tests for YOLO↔WiFi observation matching."""

    def setup_method(self):
        WifiCalibrator._instance = None

    def _make_bridge(self, match_distance_m=3.0, match_time_s=2.0):
        calibrator = WifiCalibrator(min_pairs=100)
        bridge = CalibrationBridge(
            calibrator=calibrator,
            broker="localhost",
            port=1883,
            match_distance_m=match_distance_m,
            match_time_s=match_time_s,
        )
        return bridge, calibrator

    def test_match_close_observations(self):
        """WiFi and YOLO observations in same zone, close in space+time, produce a pair."""
        bridge, calibrator = self._make_bridge()

        now = time.time()

        # Add WiFi observation
        bridge._wifi_buffer.append(_PoseRecord(
            x=10.0, y=5.0, zone="office",
            timestamp=now, source="wifi", node_id="wifi_01",
        ))

        # Add YOLO observation and trigger matching
        bridge._yolo_buffer.append(_PoseRecord(
            x=11.0, y=5.5, zone="office",
            timestamp=now + 0.5, source="yolo",
        ))
        bridge._match_and_add()

        assert len(calibrator._pairs.get("office", [])) == 1
        pair = calibrator._pairs["office"][0]
        assert pair.wifi_xy == [10.0, 5.0]
        assert pair.yolo_xy == [11.0, 5.5]

    def test_no_match_different_zones(self):
        """Observations in different zones are not matched."""
        bridge, calibrator = self._make_bridge()
        now = time.time()

        bridge._wifi_buffer.append(_PoseRecord(
            x=10.0, y=5.0, zone="kitchen",
            timestamp=now, source="wifi",
        ))
        bridge._yolo_buffer.append(_PoseRecord(
            x=10.0, y=5.0, zone="office",
            timestamp=now, source="yolo",
        ))
        bridge._match_and_add()

        assert len(calibrator._pairs) == 0

    def test_no_match_too_far(self):
        """Observations too far apart spatially are not matched."""
        bridge, calibrator = self._make_bridge(match_distance_m=2.0)
        now = time.time()

        bridge._wifi_buffer.append(_PoseRecord(
            x=10.0, y=5.0, zone="office",
            timestamp=now, source="wifi",
        ))
        bridge._yolo_buffer.append(_PoseRecord(
            x=15.0, y=5.0, zone="office",  # 5m away, > 2m threshold
            timestamp=now, source="yolo",
        ))
        bridge._match_and_add()

        assert len(calibrator._pairs) == 0

    def test_no_match_too_old(self):
        """Observations too far apart in time are not matched."""
        bridge, calibrator = self._make_bridge(match_time_s=1.0)
        now = time.time()

        bridge._wifi_buffer.append(_PoseRecord(
            x=10.0, y=5.0, zone="office",
            timestamp=now - 5.0, source="wifi",  # 5s ago
        ))
        bridge._yolo_buffer.append(_PoseRecord(
            x=10.0, y=5.0, zone="office",
            timestamp=now, source="yolo",
        ))
        bridge._match_and_add()

        assert len(calibrator._pairs) == 0

    def test_confidence_scales_with_distance(self):
        """Closer observations produce higher confidence pairs."""
        bridge, calibrator = self._make_bridge(match_distance_m=5.0)
        now = time.time()

        # Close pair
        bridge._wifi_buffer.append(_PoseRecord(
            x=10.0, y=5.0, zone="office",
            timestamp=now, source="wifi",
        ))
        bridge._yolo_buffer.append(_PoseRecord(
            x=10.5, y=5.0, zone="office",
            timestamp=now, source="yolo",
        ))
        bridge._match_and_add()

        pair = calibrator._pairs["office"][0]
        assert pair.confidence > 0.8  # 0.5m / 5m = 0.1 → confidence = 0.9

    def test_pruning_old_entries(self):
        """Old buffer entries are pruned during matching."""
        bridge, calibrator = self._make_bridge(match_time_s=1.0)
        now = time.time()

        # Add old entries
        for i in range(10):
            bridge._wifi_buffer.append(_PoseRecord(
                x=0.0, y=0.0, zone="office",
                timestamp=now - 100.0 + i, source="wifi",
            ))

        # Trigger matching — old entries should be pruned
        bridge._yolo_buffer.append(_PoseRecord(
            x=0.0, y=0.0, zone="office",
            timestamp=now, source="yolo",
        ))
        bridge._match_and_add()

        # Old wifi entries should have been pruned
        assert len(bridge._wifi_buffer) < 10

    def test_handle_yolo_message(self):
        """_handle_yolo extracts person positions from tracking payload."""
        bridge, calibrator = self._make_bridge()

        msg = MagicMock()
        msg.topic = "office/tracking/persons"
        msg.payload = json.dumps({
            "timestamp": time.time(),
            "persons": [
                {
                    "global_id": 1,
                    "floor_x_m": 10.0,
                    "floor_y_m": 5.0,
                    "zone": "office",
                    "cameras": ["cam_01"],
                    "sources": ["cam_01"],
                },
            ],
        }).encode()

        bridge._handle_yolo(msg)
        assert len(bridge._yolo_buffer) == 1
        assert bridge._yolo_buffer[0].x == 10.0

    def test_handle_yolo_skips_wifi_only_sources(self):
        """_handle_yolo skips persons with no camera sources."""
        bridge, _ = self._make_bridge()

        msg = MagicMock()
        msg.topic = "office/tracking/persons"
        msg.payload = json.dumps({
            "timestamp": time.time(),
            "persons": [
                {
                    "global_id": 1,
                    "floor_x_m": 10.0,
                    "floor_y_m": 5.0,
                    "zone": "office",
                    "cameras": [],
                    "sources": ["wifi_01"],
                },
            ],
        }).encode()

        bridge._handle_yolo(msg)
        assert len(bridge._yolo_buffer) == 0
