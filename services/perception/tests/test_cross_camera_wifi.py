"""Unit tests for WiFi tracklet association in CrossCameraTracker."""
import time

import numpy as np
import pytest

from conftest import make_embedding, make_tracked_person, make_wifi_tracked_person

# Use real-ish timestamps so tracklets don't expire in _cleanup
_NOW = time.time()


class TestCrossCameraWifi:
    """Tests for WiFi tracklet handling in CrossCameraTracker."""

    def _make_tracker(self, **kwargs):
        from tracking.cross_camera_tracker import CrossCameraTracker

        defaults = dict(
            zone_polygons={},
            reid_weight=0.5,
            spatial_weight=0.3,
            temporal_weight=0.2,
            match_threshold=0.5,
            spatial_gate_m=5.0,
            temporal_gate_s=30.0,
            tracklet_timeout_s=60.0,
            global_track_timeout_s=300.0,
            wifi_spatial_weight=0.7,
            wifi_temporal_weight=0.3,
            wifi_spatial_gate_m=8.0,
        )
        defaults.update(kwargs)
        return CrossCameraTracker(**defaults)

    def test_is_wifi_tracklet(self):
        """_is_wifi_tracklet correctly identifies WiFi vs camera tracklets."""
        from tracking.tracklet import Tracklet

        tracker = self._make_tracker()

        # WiFi tracklet
        t_wifi = Tracklet(camera_id="wifi_01", local_track_id=1)
        t_wifi.detections.append(make_wifi_tracked_person())
        assert tracker._is_wifi_tracklet(t_wifi) is True

        # Camera tracklet
        t_cam = Tracklet(camera_id="cam_01", local_track_id=1)
        t_cam.detections.append(make_tracked_person())
        assert tracker._is_wifi_tracklet(t_cam) is False

        # Empty tracklet
        t_empty = Tracklet(camera_id="x", local_track_id=1)
        assert tracker._is_wifi_tracklet(t_empty) is False

    def test_wifi_tracklet_creates_global_track(self):
        """A WiFi tracklet (no embedding) should create a global track.

        When there are no existing global tracks, the tracker creates new
        ones directly (bypasses Hungarian algorithm).
        """
        tracker = self._make_tracker()

        # No existing globals → code path goes through _create_global_track directly
        persons = [make_wifi_tracked_person(
            track_id=1,
            node_id="wifi_01",
            foot_floor=[10.0, 5.0],
            timestamp=_NOW,
        )]
        tracker.update_camera("wifi_01", persons)

        tracks = tracker.get_global_tracks()
        assert len(tracks) == 1
        assert "wifi_01" in tracks[0].camera_ids

    def test_wifi_tracklet_no_reid_weight(self):
        """WiFi cost computation uses reid_weight=0, spatial+temporal only."""
        from tracking.tracklet import Tracklet, GlobalTrack

        tracker = self._make_tracker()

        # Create a global track with a known position
        t_cam = Tracklet(camera_id="cam_01", local_track_id=1)
        p_cam = make_tracked_person(
            foot_floor=[10.0, 5.0], timestamp=1000.0
        )
        t_cam.detections.append(p_cam)
        t_cam.avg_embedding = make_embedding(seed=1)

        gtrack = GlobalTrack(
            global_id=1,
            tracklets={"cam_01": t_cam},
            last_seen=_NOW,
            floor_position=[10.0, 5.0],
            avg_embedding=make_embedding(seed=1),
        )

        # WiFi tracklet nearby
        t_wifi = Tracklet(camera_id="wifi_01", local_track_id=1)
        p_wifi = make_wifi_tracked_person(
            foot_floor=[11.0, 5.0], timestamp=_NOW + 1.0
        )
        t_wifi.detections.append(p_wifi)
        t_wifi.last_seen = _NOW + 1.0

        cost = tracker._compute_cost(t_wifi, gtrack, _NOW + 1.0)
        assert cost is not None
        # With 0 reid_weight, cost should be driven by spatial+temporal
        assert 0.0 < cost < 1.0

    def test_wifi_spatial_gate_wider(self):
        """WiFi uses wider spatial gate (8m vs 5m for camera)."""
        from tracking.tracklet import Tracklet, GlobalTrack

        tracker = self._make_tracker(
            spatial_gate_m=5.0, wifi_spatial_gate_m=8.0
        )

        gtrack = GlobalTrack(
            global_id=1,
            last_seen=_NOW,
            floor_position=[10.0, 5.0],
            avg_embedding=make_embedding(seed=1),
        )

        # 6m away — within WiFi gate (8m) but outside camera gate (5m)
        t_wifi = Tracklet(camera_id="wifi_01", local_track_id=1)
        p_wifi = make_wifi_tracked_person(
            foot_floor=[16.0, 5.0], timestamp=1000.0
        )
        t_wifi.detections.append(p_wifi)
        t_wifi.last_seen = _NOW

        cost_wifi = tracker._compute_cost(t_wifi, gtrack, _NOW)
        assert cost_wifi is not None  # Within WiFi gate

        # Same distance with camera tracklet
        t_cam = Tracklet(camera_id="cam_02", local_track_id=1)
        p_cam = make_tracked_person(
            foot_floor=[16.0, 5.0], timestamp=1000.0,
            camera_id="cam_02",
        )
        t_cam.detections.append(p_cam)
        t_cam.avg_embedding = make_embedding(seed=2)
        t_cam.last_seen = _NOW

        cost_cam = tracker._compute_cost(t_cam, gtrack, _NOW)
        assert cost_cam is None  # Outside camera gate

    def test_mixed_camera_wifi_global_track(self):
        """Both camera and WiFi tracklets create global tracks.

        With mocked linear_sum_assignment (returns empty), each source
        creates a separate global track. The key is that both source types
        coexist in the tracker.
        """
        tracker = self._make_tracker()

        # Camera detection creates first global track
        cam_persons = [make_tracked_person(
            track_id=1, camera_id="cam_01",
            foot_floor=[10.0, 5.0], timestamp=_NOW,
        )]
        tracker.update_camera("cam_01", cam_persons)

        # WiFi detection creates second global track (or associates)
        wifi_persons = [make_wifi_tracked_person(
            track_id=1, node_id="wifi_01",
            foot_floor=[10.5, 5.0], timestamp=_NOW + 1.0,
        )]
        tracker.update_camera("wifi_01", wifi_persons)

        tracks = tracker.get_global_tracks()
        assert len(tracks) >= 1

        total_sources = set()
        for t in tracks:
            total_sources.update(t.camera_ids)
        assert "cam_01" in total_sources
        assert "wifi_01" in total_sources
