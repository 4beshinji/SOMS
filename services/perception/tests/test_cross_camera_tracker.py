"""Unit tests for cross_camera_tracker — confirmation, re-ID threshold, merging."""
import time

import numpy as np
import pytest

from conftest import make_embedding, make_tracked_person


def _now():
    return time.time()


def _make_tracker(**kwargs):
    """Create a CrossCameraTracker with test-friendly defaults."""
    from tracking.cross_camera_tracker import CrossCameraTracker

    defaults = dict(
        zone_polygons={},
        merge_check_interval_s=0.0,  # always eligible to merge
    )
    defaults.update(kwargs)
    return CrossCameraTracker(**defaults)


def _feed_detections(tracker, camera_id, detections):
    """Feed detections into the tracker (calls update_camera)."""
    tracker.update_camera(camera_id, detections)


# ── Confirmation Period ───────────────────────────────────────────


class TestConfirmationPeriod:
    """Tracklets must accumulate enough hits & age before getting a global ID."""

    def test_unconfirmed_tracklet_no_global_id(self):
        """Single detection should NOT create a global track."""
        tracker = _make_tracker(min_hits_for_global=3, min_age_s_for_global=2.0)

        ts = _now()
        det = make_tracked_person(track_id=1, camera_id="cam_a", timestamp=ts)
        _feed_detections(tracker, "cam_a", [det])

        assert len(tracker.get_global_tracks()) == 0

    def test_confirmed_tracklet_gets_global_id(self):
        """Tracklet with enough hits over enough time gets a global ID."""
        tracker = _make_tracker(min_hits_for_global=3, min_age_s_for_global=0.0)

        ts = _now()
        emb = make_embedding(seed=42)
        for i in range(3):
            det = make_tracked_person(
                track_id=1, camera_id="cam_a",
                reid_embedding=emb, timestamp=ts + i * 0.01,
            )
            _feed_detections(tracker, "cam_a", [det])

        tracks = tracker.get_global_tracks()
        assert len(tracks) == 1

    def test_wifi_bypasses_confirmation(self):
        """WiFi tracklets skip the confirmation period."""
        from conftest import make_wifi_tracked_person

        tracker = _make_tracker(min_hits_for_global=10, min_age_s_for_global=10.0)

        ts = _now()
        det = make_wifi_tracked_person(track_id=1, node_id="wifi_01", timestamp=ts)
        _feed_detections(tracker, "wifi_01", [det])

        # WiFi tracklet has zero embedding → avg_embedding stays None → no global track
        # But the confirmation check itself should pass for WiFi
        tracklet_key = ("wifi_01", 1)
        assert tracklet_key in tracker._tracklets
        tracklet = tracker._tracklets[tracklet_key]
        assert tracker._is_confirmed(tracklet, ts) is True


# ── Re-ID Threshold ──────────────────────────────────────────────


class TestReIDThreshold:
    """Re-identification uses configurable threshold instead of hardcoded 0.7."""

    def test_reidentify_with_configured_threshold(self):
        """Same embedding should re-identify when threshold is 0.55."""
        tracker = _make_tracker(
            reid_match_threshold=0.55,
            min_hits_for_global=1,
            min_age_s_for_global=0.0,
            global_track_timeout_s=1.0,
        )

        ts = _now()
        emb = make_embedding(seed=10)
        det = make_tracked_person(
            track_id=1, camera_id="cam_a",
            reid_embedding=emb, timestamp=ts,
        )
        _feed_detections(tracker, "cam_a", [det])
        assert len(tracker.get_global_tracks()) == 1
        old_gid = tracker.get_global_tracks()[0].global_id

        # Force expire by manually manipulating last_seen
        for g in tracker._global_tracks.values():
            g.last_seen = ts - 100.0
        for t in tracker._tracklets.values():
            t.last_seen = ts - 100.0
        tracker._cleanup(ts)
        assert len(tracker.get_global_tracks()) == 0
        assert len(tracker._embedding_history) == 1

        tracker._tracklets.clear()

        # New detection with same embedding → should re-identify
        det2 = make_tracked_person(
            track_id=2, camera_id="cam_a",
            reid_embedding=emb, timestamp=ts + 1.0,
        )
        _feed_detections(tracker, "cam_a", [det2])

        tracks = tracker.get_global_tracks()
        assert len(tracks) == 1
        assert tracks[0].global_id == old_gid

    def test_reidentify_rejects_below_threshold(self):
        """Similarity below threshold should NOT re-identify."""
        tracker = _make_tracker(
            reid_match_threshold=0.9,
            min_hits_for_global=1,
            min_age_s_for_global=0.0,
            global_track_timeout_s=1.0,
        )

        ts = _now()
        emb1 = make_embedding(seed=10)
        det = make_tracked_person(
            track_id=1, camera_id="cam_a",
            reid_embedding=emb1, timestamp=ts,
        )
        _feed_detections(tracker, "cam_a", [det])
        old_gid = tracker.get_global_tracks()[0].global_id

        # Force expire
        for g in tracker._global_tracks.values():
            g.last_seen = ts - 100.0
        for t in tracker._tracklets.values():
            t.last_seen = ts - 100.0
        tracker._cleanup(ts)
        tracker._tracklets.clear()

        # Different embedding → low similarity → new ID
        emb2 = make_embedding(seed=99)
        det2 = make_tracked_person(
            track_id=2, camera_id="cam_a",
            reid_embedding=emb2, timestamp=_now(),
        )
        _feed_detections(tracker, "cam_a", [det2])

        tracks = tracker.get_global_tracks()
        assert len(tracks) == 1
        assert tracks[0].global_id != old_gid


# ── Global Track Merging ─────────────────────────────────────────


class TestGlobalTrackMerging:
    """Active global tracks with similar embeddings should be merged."""

    def _create_two_global_tracks(self, tracker, emb_a=None, emb_b=None,
                                   pos_a=None, pos_b=None):
        """Helper: create two global tracks on different cameras."""
        if emb_a is None:
            emb_a = make_embedding(seed=1)
        if emb_b is None:
            emb_b = make_embedding(seed=1)
        if pos_a is None:
            pos_a = [1.0, 1.0]
        if pos_b is None:
            pos_b = [1.5, 1.5]

        ts = _now()
        det_a = make_tracked_person(
            track_id=1, camera_id="cam_a",
            reid_embedding=emb_a, foot_floor=pos_a, timestamp=ts,
        )
        _feed_detections(tracker, "cam_a", [det_a])

        det_b = make_tracked_person(
            track_id=1, camera_id="cam_b",
            reid_embedding=emb_b, foot_floor=pos_b, timestamp=ts,
        )
        _feed_detections(tracker, "cam_b", [det_b])

    def test_merge_similar_tracks(self):
        """Two tracks with identical embeddings and close positions merge."""
        tracker = _make_tracker(
            min_hits_for_global=1, min_age_s_for_global=0.0,
            merge_reid_threshold=0.5, merge_spatial_gate_m=5.0,
        )

        emb = make_embedding(seed=42)
        self._create_two_global_tracks(tracker, emb_a=emb, emb_b=emb)

        assert len(tracker.get_global_tracks()) == 1

    def test_no_merge_different_persons(self):
        """Two tracks with different embeddings and far apart stay separate.

        At dist=5.66m, spatial_bonus ≈ 0.5/(32+0.1) ≈ 0.016.
        Combined with low ReID sim, total score stays below threshold 0.8.
        """
        tracker = _make_tracker(
            min_hits_for_global=1, min_age_s_for_global=0.0,
            merge_reid_threshold=0.8, merge_spatial_gate_m=10.0,
        )

        emb_a = make_embedding(seed=1)
        emb_b = make_embedding(seed=999)
        self._create_two_global_tracks(
            tracker, emb_a=emb_a, emb_b=emb_b,
            pos_a=[1.0, 1.0], pos_b=[5.0, 5.0],
        )

        assert len(tracker.get_global_tracks()) == 2

    def test_no_merge_shared_camera(self):
        """Tracks sharing a camera are not merged (same person can't split)."""
        tracker = _make_tracker(
            min_hits_for_global=1, min_age_s_for_global=0.0,
            merge_reid_threshold=0.3, merge_spatial_gate_m=10.0,
        )

        ts = _now()
        emb = make_embedding(seed=42)
        det1 = make_tracked_person(
            track_id=1, camera_id="cam_a",
            reid_embedding=emb, foot_floor=[1.0, 1.0], timestamp=ts,
        )
        det2 = make_tracked_person(
            track_id=2, camera_id="cam_a",
            reid_embedding=emb, foot_floor=[1.5, 1.5], timestamp=ts,
        )
        _feed_detections(tracker, "cam_a", [det1, det2])

        tracks = tracker.get_global_tracks()
        assert len(tracks) == 2

    def test_no_merge_far_apart(self):
        """Tracks beyond spatial gate don't merge even with similar embeddings."""
        tracker = _make_tracker(
            min_hits_for_global=1, min_age_s_for_global=0.0,
            merge_reid_threshold=0.5, merge_spatial_gate_m=1.0,
        )

        ts = _now()
        emb = make_embedding(seed=42)
        # Use non-zero positions that are far apart
        det_a = make_tracked_person(
            track_id=1, camera_id="cam_a",
            reid_embedding=emb, foot_floor=[1.0, 1.0], timestamp=ts,
        )
        _feed_detections(tracker, "cam_a", [det_a])

        det_b = make_tracked_person(
            track_id=1, camera_id="cam_b",
            reid_embedding=emb, foot_floor=[10.0, 10.0], timestamp=ts,
        )
        _feed_detections(tracker, "cam_b", [det_b])

        tracks = tracker.get_global_tracks()
        assert len(tracks) == 2

    def test_merge_keeps_lower_id(self):
        """After merge, the surviving track has the lower global_id."""
        tracker = _make_tracker(
            min_hits_for_global=1, min_age_s_for_global=0.0,
            merge_reid_threshold=0.5, merge_spatial_gate_m=5.0,
        )

        emb = make_embedding(seed=42)
        self._create_two_global_tracks(tracker, emb_a=emb, emb_b=emb)

        tracks = tracker.get_global_tracks()
        assert len(tracks) == 1
        assert tracks[0].global_id == 1

    def test_merge_transfers_tracklets(self):
        """After merge, the surviving track contains tracklets from both cameras."""
        tracker = _make_tracker(
            min_hits_for_global=1, min_age_s_for_global=0.0,
            merge_reid_threshold=0.5, merge_spatial_gate_m=5.0,
        )

        emb = make_embedding(seed=42)
        self._create_two_global_tracks(tracker, emb_a=emb, emb_b=emb)

        tracks = tracker.get_global_tracks()
        assert len(tracks) == 1
        assert "cam_a" in tracks[0].tracklets
        assert "cam_b" in tracks[0].tracklets

    def test_merge_updates_tracklet_dict(self):
        """After merge, _tracklets dict entries point to the surviving global_id."""
        tracker = _make_tracker(
            min_hits_for_global=1, min_age_s_for_global=0.0,
            merge_reid_threshold=0.5, merge_spatial_gate_m=5.0,
        )

        emb = make_embedding(seed=42)
        self._create_two_global_tracks(tracker, emb_a=emb, emb_b=emb)

        surviving_id = tracker.get_global_tracks()[0].global_id
        for key, tracklet in tracker._tracklets.items():
            if tracklet.global_id is not None:
                assert tracklet.global_id == surviving_id


# ── EMA Alpha ────────────────────────────────────────────────────


class TestEMAAlpha:
    """Tracklet embedding_alpha parameter is respected."""

    def test_custom_alpha(self):
        """Tracklet with custom alpha uses it in EMA calculation."""
        from tracking.tracklet import Tracklet

        emb1 = make_embedding(seed=1)
        emb2 = make_embedding(seed=2)

        t = Tracklet(camera_id="cam_01", local_track_id=1, embedding_alpha=0.5)

        p1 = make_tracked_person(reid_embedding=emb1, timestamp=100.0)
        t.detections.append(p1)
        t.update_embedding()

        p2 = make_tracked_person(reid_embedding=emb2, timestamp=200.0)
        t.detections.append(p2)
        t.update_embedding()

        expected = 0.5 * emb2 + 0.5 * emb1
        expected /= np.linalg.norm(expected)

        assert t.avg_embedding is not None
        assert np.allclose(t.avg_embedding, expected, atol=1e-5)
