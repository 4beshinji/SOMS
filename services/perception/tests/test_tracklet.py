"""Unit tests for tracking.tracklet — TrackedPerson, Tracklet, GlobalTrack."""
import numpy as np
import pytest

from conftest import make_embedding, make_tracked_person


# ── TrackedPerson ────────────────────────────────────────────────


class TestTrackedPerson:
    """Tests for the TrackedPerson dataclass."""

    def test_create_tracked_person(self):
        """TrackedPerson stores all fields correctly."""
        emb = make_embedding(seed=42)
        p = make_tracked_person(
            track_id=5,
            camera_id="cam_a",
            bbox_px=[10.0, 20.0, 30.0, 40.0],
            foot_px=[20.0, 40.0],
            foot_floor=[1.0, 2.0],
            confidence=0.85,
            reid_embedding=emb,
            timestamp=999.0,
        )
        assert p.track_id == 5
        assert p.camera_id == "cam_a"
        assert p.bbox_px == [10.0, 20.0, 30.0, 40.0]
        assert p.foot_px == [20.0, 40.0]
        assert p.foot_floor == [1.0, 2.0]
        assert p.confidence == 0.85
        assert np.array_equal(p.reid_embedding, emb)
        assert p.timestamp == 999.0

    def test_default_values(self):
        """make_tracked_person helper fills sensible defaults."""
        p = make_tracked_person()
        assert p.track_id == 1
        assert p.camera_id == "cam_01"
        assert p.confidence == 0.9
        assert p.reid_embedding.shape == (512,)
        # Embedding should be L2-normalized
        assert abs(np.linalg.norm(p.reid_embedding) - 1.0) < 1e-5


# ── Tracklet ─────────────────────────────────────────────────────


class TestTracklet:
    """Tests for the Tracklet dataclass and its methods."""

    def test_create_empty_tracklet(self):
        """A new Tracklet has empty detections and no global_id."""
        from tracking.tracklet import Tracklet

        t = Tracklet(camera_id="cam_01", local_track_id=10)
        assert t.camera_id == "cam_01"
        assert t.local_track_id == 10
        assert t.global_id is None
        assert len(t.detections) == 0
        assert t.last_seen == 0.0
        assert t.avg_embedding is None

    def test_latest_floor_position_empty(self):
        """latest_floor_position returns None when no detections exist."""
        from tracking.tracklet import Tracklet

        t = Tracklet(camera_id="cam_01", local_track_id=1)
        assert t.latest_floor_position is None

    def test_latest_floor_position_with_detections(self):
        """latest_floor_position returns the most recent detection's foot_floor."""
        from tracking.tracklet import Tracklet

        t = Tracklet(camera_id="cam_01", local_track_id=1)
        p1 = make_tracked_person(foot_floor=[1.0, 2.0], timestamp=100.0)
        p2 = make_tracked_person(foot_floor=[3.0, 4.0], timestamp=200.0)
        t.detections.append(p1)
        t.detections.append(p2)
        assert t.latest_floor_position == [3.0, 4.0]

    def test_update_embedding_first_detection(self):
        """First detection sets avg_embedding as a copy of the embedding."""
        from tracking.tracklet import Tracklet

        emb = make_embedding(seed=7)
        t = Tracklet(camera_id="cam_01", local_track_id=1)
        p = make_tracked_person(reid_embedding=emb)
        t.detections.append(p)
        t.update_embedding()

        assert t.avg_embedding is not None
        assert np.allclose(t.avg_embedding, emb)
        # Should be a copy, not the same object
        assert t.avg_embedding is not emb

    def test_update_embedding_ema(self):
        """Subsequent detections use exponential moving average (alpha=0.3)."""
        from tracking.tracklet import Tracklet

        emb1 = make_embedding(seed=1)
        emb2 = make_embedding(seed=2)

        t = Tracklet(camera_id="cam_01", local_track_id=1)

        # First detection
        p1 = make_tracked_person(reid_embedding=emb1, timestamp=100.0)
        t.detections.append(p1)
        t.update_embedding()

        # Second detection
        p2 = make_tracked_person(reid_embedding=emb2, timestamp=200.0)
        t.detections.append(p2)
        t.update_embedding()

        # Expected: alpha * new + (1-alpha) * old, then re-normalized
        expected = 0.3 * emb2 + 0.7 * emb1
        expected /= np.linalg.norm(expected)

        assert t.avg_embedding is not None
        assert np.allclose(t.avg_embedding, expected, atol=1e-5)

    def test_update_embedding_no_detections(self):
        """update_embedding is a no-op when no detections exist."""
        from tracking.tracklet import Tracklet

        t = Tracklet(camera_id="cam_01", local_track_id=1)
        t.update_embedding()
        assert t.avg_embedding is None

    def test_update_embedding_result_is_unit_vector(self):
        """After update, avg_embedding should be L2-normalized."""
        from tracking.tracklet import Tracklet

        t = Tracklet(camera_id="cam_01", local_track_id=1)

        for i in range(5):
            p = make_tracked_person(reid_embedding=make_embedding(seed=i), timestamp=float(i))
            t.detections.append(p)
            t.update_embedding()

        assert t.avg_embedding is not None
        norm = np.linalg.norm(t.avg_embedding)
        assert abs(norm - 1.0) < 1e-5

    def test_detections_deque_maxlen(self):
        """Tracklet detections deque enforces maxlen=30."""
        from tracking.tracklet import Tracklet

        t = Tracklet(camera_id="cam_01", local_track_id=1)

        for i in range(50):
            p = make_tracked_person(track_id=i, timestamp=float(i))
            t.detections.append(p)

        assert len(t.detections) == 30
        # First detection should be the 21st one added (index 20)
        assert t.detections[0].track_id == 20


# ── GlobalTrack ──────────────────────────────────────────────────


class TestGlobalTrack:
    """Tests for the GlobalTrack dataclass and its methods."""

    def test_create_global_track_defaults(self):
        """GlobalTrack has sensible default values."""
        from tracking.tracklet import GlobalTrack

        g = GlobalTrack(global_id=1)
        assert g.global_id == 1
        assert g.tracklets == {}
        assert g.last_seen == 0.0
        assert g.floor_position == [0.0, 0.0]
        assert g.zone_id == ""
        assert g.first_seen == 0.0
        assert g.avg_embedding is None

    def test_duration_sec_no_times(self):
        """duration_sec returns 0.0 when first_seen or last_seen is 0."""
        from tracking.tracklet import GlobalTrack

        g = GlobalTrack(global_id=1)
        assert g.duration_sec == 0.0

    def test_duration_sec_with_times(self):
        """duration_sec returns the difference between last_seen and first_seen."""
        from tracking.tracklet import GlobalTrack

        g = GlobalTrack(global_id=1, first_seen=100.0, last_seen=250.0)
        assert g.duration_sec == 150.0

    def test_camera_ids_empty(self):
        """camera_ids returns empty list when no tracklets."""
        from tracking.tracklet import GlobalTrack

        g = GlobalTrack(global_id=1)
        assert g.camera_ids == []

    def test_camera_ids_with_tracklets(self):
        """camera_ids returns list of camera IDs from tracklets."""
        from tracking.tracklet import GlobalTrack, Tracklet

        t1 = Tracklet(camera_id="cam_01", local_track_id=1)
        t2 = Tracklet(camera_id="cam_02", local_track_id=2)

        g = GlobalTrack(
            global_id=1,
            tracklets={"cam_01": t1, "cam_02": t2},
        )
        ids = g.camera_ids
        assert sorted(ids) == ["cam_01", "cam_02"]

    def test_update_position_from_most_recent_tracklet(self):
        """update_position selects the most recently seen tracklet position."""
        from tracking.tracklet import GlobalTrack, Tracklet

        t1 = Tracklet(camera_id="cam_01", local_track_id=1, last_seen=100.0)
        p1 = make_tracked_person(foot_floor=[1.0, 1.0], timestamp=100.0)
        t1.detections.append(p1)

        t2 = Tracklet(camera_id="cam_02", local_track_id=2, last_seen=200.0)
        p2 = make_tracked_person(foot_floor=[5.0, 5.0], timestamp=200.0)
        t2.detections.append(p2)

        g = GlobalTrack(
            global_id=1,
            tracklets={"cam_01": t1, "cam_02": t2},
        )
        g.update_position()

        assert g.floor_position == [5.0, 5.0]
        assert g.last_seen == 200.0

    def test_update_position_skips_empty_tracklets(self):
        """update_position ignores tracklets with no detections."""
        from tracking.tracklet import GlobalTrack, Tracklet

        t_empty = Tracklet(camera_id="cam_01", local_track_id=1, last_seen=500.0)
        t_with = Tracklet(camera_id="cam_02", local_track_id=2, last_seen=100.0)
        p = make_tracked_person(foot_floor=[3.0, 4.0], timestamp=100.0)
        t_with.detections.append(p)

        g = GlobalTrack(
            global_id=1,
            tracklets={"cam_01": t_empty, "cam_02": t_with},
        )
        g.update_position()

        # t_empty has higher last_seen but no floor position
        assert g.floor_position == [3.0, 4.0]
        assert g.last_seen == 100.0

    def test_update_embedding_single_tracklet(self):
        """update_embedding with one tracklet produces its normalized embedding."""
        from tracking.tracklet import GlobalTrack, Tracklet

        emb = make_embedding(seed=42)
        t = Tracklet(camera_id="cam_01", local_track_id=1)
        t.avg_embedding = emb

        g = GlobalTrack(global_id=1, tracklets={"cam_01": t})
        g.update_embedding()

        assert g.avg_embedding is not None
        assert np.allclose(g.avg_embedding, emb, atol=1e-5)

    def test_update_embedding_multiple_tracklets(self):
        """update_embedding averages embeddings from all tracklets."""
        from tracking.tracklet import GlobalTrack, Tracklet

        emb1 = make_embedding(seed=1)
        emb2 = make_embedding(seed=2)

        t1 = Tracklet(camera_id="cam_01", local_track_id=1)
        t1.avg_embedding = emb1
        t2 = Tracklet(camera_id="cam_02", local_track_id=2)
        t2.avg_embedding = emb2

        g = GlobalTrack(global_id=1, tracklets={"cam_01": t1, "cam_02": t2})
        g.update_embedding()

        expected = np.stack([emb1, emb2]).mean(axis=0)
        expected /= np.linalg.norm(expected)

        assert g.avg_embedding is not None
        assert np.allclose(g.avg_embedding, expected, atol=1e-5)

    def test_update_embedding_skips_none(self):
        """update_embedding ignores tracklets with None avg_embedding."""
        from tracking.tracklet import GlobalTrack, Tracklet

        emb = make_embedding(seed=10)

        t1 = Tracklet(camera_id="cam_01", local_track_id=1)
        t1.avg_embedding = emb
        t2 = Tracklet(camera_id="cam_02", local_track_id=2)
        t2.avg_embedding = None  # No embedding yet

        g = GlobalTrack(global_id=1, tracklets={"cam_01": t1, "cam_02": t2})
        g.update_embedding()

        assert g.avg_embedding is not None
        assert np.allclose(g.avg_embedding, emb, atol=1e-5)

    def test_update_embedding_no_tracklet_embeddings(self):
        """update_embedding is a no-op when no tracklets have embeddings."""
        from tracking.tracklet import GlobalTrack, Tracklet

        t = Tracklet(camera_id="cam_01", local_track_id=1)
        # avg_embedding is None by default

        g = GlobalTrack(global_id=1, tracklets={"cam_01": t})
        g.update_embedding()

        assert g.avg_embedding is None
