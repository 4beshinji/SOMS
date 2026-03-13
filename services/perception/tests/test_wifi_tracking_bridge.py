"""Unit tests for WifiTrackingBridge — MQTT message parsing + TrackedPerson conversion."""
import json
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from conftest import make_wifi_tracked_person


class TestWifiTrackingBridge:
    """Tests for WifiTrackingBridge message handling."""

    def _make_bridge(self):
        from tracking.wifi_tracking_bridge import WifiTrackingBridge

        mock_tracker = MagicMock()
        bridge = WifiTrackingBridge(
            cross_tracker=mock_tracker,
            broker="localhost",
            port=1883,
        )
        return bridge, mock_tracker

    def _make_mqtt_msg(self, topic: str, payload: dict):
        msg = MagicMock()
        msg.topic = topic
        msg.payload = json.dumps(payload).encode()
        return msg

    def test_parse_wifi_pose_message(self):
        """Valid WiFi pose message produces TrackedPerson with source_type='wifi'."""
        bridge, tracker = self._make_bridge()

        payload = {
            "timestamp": 1000.0,
            "persons": [
                {"id": 1, "x": 10.0, "y": 5.0, "confidence": 0.7},
                {"id": 2, "x": 12.0, "y": 6.0, "confidence": 0.5},
            ],
        }
        msg = self._make_mqtt_msg("office/main/wifi-pose/wifi_01", payload)
        bridge._handle_message(msg)

        tracker.update_camera.assert_called_once()
        call_args = tracker.update_camera.call_args
        assert call_args[0][0] == "wifi_01"

        persons = call_args[0][1]
        assert len(persons) == 2

        p1 = persons[0]
        assert p1.source_type == "wifi"
        assert p1.track_id == 1
        assert p1.foot_floor == [10.0, 5.0]
        assert p1.confidence == 0.7
        assert p1.camera_id == "wifi_01"
        assert np.linalg.norm(p1.reid_embedding) < 1e-6
        assert p1.bbox_px == [0.0, 0.0, 0.0, 0.0]

    def test_empty_persons_list(self):
        """Empty persons list does not call update_camera."""
        bridge, tracker = self._make_bridge()

        payload = {"timestamp": 1000.0, "persons": []}
        msg = self._make_mqtt_msg("office/main/wifi-pose/wifi_01", payload)
        bridge._handle_message(msg)

        tracker.update_camera.assert_not_called()

    def test_missing_persons_key(self):
        """Missing 'persons' key does not call update_camera."""
        bridge, tracker = self._make_bridge()

        payload = {"timestamp": 1000.0}
        msg = self._make_mqtt_msg("office/main/wifi-pose/wifi_01", payload)
        bridge._handle_message(msg)

        tracker.update_camera.assert_not_called()

    def test_short_topic_ignored(self):
        """Topic with fewer than 4 parts is silently ignored."""
        bridge, tracker = self._make_bridge()

        payload = {"persons": [{"id": 1, "x": 1.0, "y": 2.0}]}
        msg = self._make_mqtt_msg("office/main", payload)
        bridge._handle_message(msg)

        tracker.update_camera.assert_not_called()

    def test_timestamp_fallback(self):
        """Missing timestamp in payload uses current time."""
        bridge, tracker = self._make_bridge()

        payload = {"persons": [{"id": 1, "x": 1.0, "y": 2.0}]}
        msg = self._make_mqtt_msg("office/main/wifi-pose/wifi_01", payload)

        before = time.time()
        bridge._handle_message(msg)
        after = time.time()

        persons = tracker.update_camera.call_args[0][1]
        assert before <= persons[0].timestamp <= after
