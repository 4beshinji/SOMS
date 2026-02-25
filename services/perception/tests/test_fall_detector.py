"""Tests for FallDetector — geometric heuristic fall detection.

Uses synthetic keypoints to test all posture scenarios without GPU/camera.
"""

import sys
from pathlib import Path

# Ensure perception src is on path
PERCEPTION_SRC = str(Path(__file__).resolve().parent.parent / "src")
if PERCEPTION_SRC not in sys.path:
    sys.path.insert(0, PERCEPTION_SRC)

import time
from unittest.mock import patch

import pytest

from fall_detector import (
    FallDetector,
    FallAlert,
    PersonState,
    PostureSnapshot,
    PersonTracker,
    _NOSE,
    _L_SHOULDER,
    _R_SHOULDER,
    _L_HIP,
    _R_HIP,
    _L_ANKLE,
    _R_ANKLE,
)


# ---------------------------------------------------------------------------
# Synthetic keypoint generators
# ---------------------------------------------------------------------------

def _make_kp(positions: dict) -> tuple[list[list[float]], list[float]]:
    """
    Build 17-keypoint arrays from a sparse dict of {index: (x, y)}.
    Missing keypoints get (0, 0) with confidence 0.0.
    """
    kp = [[0.0, 0.0] for _ in range(17)]
    conf = [0.0] * 17
    for idx, (x, y) in positions.items():
        kp[idx] = [float(x), float(y)]
        conf[idx] = 0.9
    return kp, conf


def standing_person(cx: float = 300, cy_top: float = 50):
    """Upright person — shoulders above hips, vertical torso."""
    kp, conf = _make_kp({
        _NOSE: (cx, cy_top),
        _L_SHOULDER: (cx - 30, cy_top + 60),
        _R_SHOULDER: (cx + 30, cy_top + 60),
        _L_HIP: (cx - 20, cy_top + 180),
        _R_HIP: (cx + 20, cy_top + 180),
        _L_ANKLE: (cx - 20, cy_top + 340),
        _R_ANKLE: (cx + 20, cy_top + 340),
    })
    bbox = [cx - 50, cy_top - 10, cx + 50, cy_top + 350]
    return {"bbox": bbox, "keypoints": kp, "keypoint_conf": conf}


def fallen_person(cx: float = 300, cy: float = 400):
    """Person lying flat on floor — horizontal torso, head at hip level."""
    kp, conf = _make_kp({
        _NOSE: (cx - 120, cy + 10),        # Head at same height as hips
        _L_SHOULDER: (cx - 80, cy - 15),
        _R_SHOULDER: (cx - 80, cy + 15),
        _L_HIP: (cx + 50, cy - 10),
        _R_HIP: (cx + 50, cy + 10),
        _L_ANKLE: (cx + 160, cy - 15),
        _R_ANKLE: (cx + 160, cy + 15),
    })
    bbox = [cx - 140, cy - 30, cx + 180, cy + 30]
    return {"bbox": bbox, "keypoints": kp, "keypoint_conf": conf}


def sitting_person(cx: float = 300, cy_top: float = 200):
    """Person sitting in chair — torso mostly upright."""
    kp, conf = _make_kp({
        _NOSE: (cx, cy_top),
        _L_SHOULDER: (cx - 25, cy_top + 50),
        _R_SHOULDER: (cx + 25, cy_top + 50),
        _L_HIP: (cx - 20, cy_top + 130),
        _R_HIP: (cx + 20, cy_top + 130),
        _L_ANKLE: (cx - 30, cy_top + 220),
        _R_ANKLE: (cx + 30, cy_top + 220),
    })
    bbox = [cx - 45, cy_top - 10, cx + 45, cy_top + 230]
    return {"bbox": bbox, "keypoints": kp, "keypoint_conf": conf}


def lying_on_couch(cx: float = 300, cy: float = 350):
    """Person lying on couch — horizontal but on furniture."""
    kp, conf = _make_kp({
        _NOSE: (cx - 100, cy),
        _L_SHOULDER: (cx - 60, cy - 15),
        _R_SHOULDER: (cx - 60, cy + 15),
        _L_HIP: (cx + 50, cy - 10),
        _R_HIP: (cx + 50, cy + 10),
        _L_ANKLE: (cx + 150, cy - 15),
        _R_ANKLE: (cx + 150, cy + 15),
    })
    bbox = [cx - 120, cy - 30, cx + 170, cy + 30]
    return {"bbox": bbox, "keypoints": kp, "keypoint_conf": conf}


def bending_person(cx: float = 300, cy_top: float = 100):
    """Person bending forward — torso at ~45 degrees."""
    kp, conf = _make_kp({
        _NOSE: (cx + 40, cy_top + 60),
        _L_SHOULDER: (cx + 20, cy_top + 40),
        _R_SHOULDER: (cx + 60, cy_top + 40),
        _L_HIP: (cx - 15, cy_top + 150),
        _R_HIP: (cx + 25, cy_top + 150),
        _L_ANKLE: (cx - 20, cy_top + 300),
        _R_ANKLE: (cx + 20, cy_top + 300),
    })
    bbox = [cx - 40, cy_top - 10, cx + 80, cy_top + 310]
    return {"bbox": bbox, "keypoints": kp, "keypoint_conf": conf}


def _couch_bbox(cx: float = 300, cy: float = 350):
    """Furniture bbox matching lying_on_couch position."""
    return {
        "class": "couch",
        "bbox": [cx - 150, cy - 50, cx + 200, cy + 50],
        "confidence": 0.85,
    }


def _chair_bbox(cx: float = 300, cy_top: float = 200):
    """Furniture bbox matching sitting_person position."""
    return {
        "class": "chair",
        "bbox": [cx - 50, cy_top + 80, cx + 50, cy_top + 250],
        "confidence": 0.80,
    }


# ---------------------------------------------------------------------------
# TestTorsoAngle
# ---------------------------------------------------------------------------

class TestTorsoAngle:
    def test_upright_near_zero(self):
        person = standing_person()
        angle = FallDetector._torso_angle(
            person["keypoints"], person["keypoint_conf"]
        )
        assert angle is not None
        assert angle < 15.0, f"Standing person angle should be near 0, got {angle:.1f}"

    def test_fallen_near_ninety(self):
        person = fallen_person()
        angle = FallDetector._torso_angle(
            person["keypoints"], person["keypoint_conf"]
        )
        assert angle is not None
        assert angle > 60.0, f"Fallen person angle should be near 90, got {angle:.1f}"

    def test_missing_keypoints_returns_none(self):
        kp = [[0.0, 0.0] for _ in range(17)]
        conf = [0.0] * 17  # All low confidence
        angle = FallDetector._torso_angle(kp, conf)
        assert angle is None


# ---------------------------------------------------------------------------
# TestHeadBelowHips
# ---------------------------------------------------------------------------

class TestHeadBelowHips:
    def test_standing_false(self):
        person = standing_person()
        assert FallDetector._head_below_hips(
            person["keypoints"], person["keypoint_conf"]
        ) is False

    def test_fallen_true(self):
        person = fallen_person()
        result = FallDetector._head_below_hips(
            person["keypoints"], person["keypoint_conf"]
        )
        assert result is True

    def test_missing_nose_returns_false(self):
        person = standing_person()
        person["keypoint_conf"][_NOSE] = 0.0
        assert FallDetector._head_below_hips(
            person["keypoints"], person["keypoint_conf"]
        ) is False


# ---------------------------------------------------------------------------
# TestBboxIoU
# ---------------------------------------------------------------------------

class TestBboxIoU:
    def test_no_overlap(self):
        iou = FallDetector._bbox_iou([0, 0, 10, 10], [20, 20, 30, 30])
        assert iou == 0.0

    def test_perfect_overlap(self):
        iou = FallDetector._bbox_iou([0, 0, 10, 10], [0, 0, 10, 10])
        assert abs(iou - 1.0) < 1e-6

    def test_partial_overlap(self):
        iou = FallDetector._bbox_iou([0, 0, 10, 10], [5, 5, 15, 15])
        # Intersection: 5x5=25, Union: 100+100-25=175
        assert abs(iou - 25 / 175) < 1e-6

    def test_contained(self):
        iou = FallDetector._bbox_iou([0, 0, 20, 20], [5, 5, 15, 15])
        # Intersection: 100, Union: 400+100-100=400
        assert abs(iou - 100 / 400) < 1e-6


# ---------------------------------------------------------------------------
# TestPointInBbox
# ---------------------------------------------------------------------------

class TestPointInBbox:
    def test_inside(self):
        assert FallDetector._point_in_bbox([5, 5], [0, 0, 10, 10]) is True

    def test_outside(self):
        assert FallDetector._point_in_bbox([15, 5], [0, 0, 10, 10]) is False

    def test_on_edge(self):
        assert FallDetector._point_in_bbox([10, 10], [0, 0, 10, 10]) is True


# ---------------------------------------------------------------------------
# TestAnkleShoulderRatio
# ---------------------------------------------------------------------------

class TestAnkleShoulderRatio:
    def test_standing_near_one(self):
        person = standing_person()
        ratio = FallDetector._ankle_shoulder_ratio(
            person["keypoints"], person["keypoint_conf"]
        )
        # Standing: ankles ~same width as shoulders
        assert 0.3 <= ratio <= 1.5

    def test_missing_keypoints_returns_one(self):
        kp = [[0.0, 0.0] for _ in range(17)]
        conf = [0.0] * 17
        ratio = FallDetector._ankle_shoulder_ratio(kp, conf)
        assert ratio == 1.0


# ---------------------------------------------------------------------------
# TestFallConfidence
# ---------------------------------------------------------------------------

class TestFallConfidence:
    def setup_method(self):
        self.detector = FallDetector()

    def test_standing_low_score(self):
        person = standing_person()
        snap = self.detector._compute_posture(person, [], time.time())
        tracker = PersonTracker(tracker_id=0, state_entered_at=time.time())
        conf = self.detector._compute_fall_confidence(snap, tracker)
        assert conf < 0.3, f"Standing person should have low confidence, got {conf:.2f}"

    def test_fallen_high_score(self):
        person = fallen_person()
        snap = self.detector._compute_posture(person, [], time.time())
        tracker = PersonTracker(tracker_id=0, state_entered_at=time.time())
        conf = self.detector._compute_fall_confidence(snap, tracker)
        assert conf >= 0.5, f"Fallen person should have high confidence, got {conf:.2f}"

    def test_couch_penalty_reduces_score(self):
        """Lying on couch should score significantly lower than lying on floor."""
        person_floor = fallen_person()
        person_couch = lying_on_couch()
        couch = _couch_bbox()
        ts = time.time()

        snap_floor = self.detector._compute_posture(person_floor, [], ts)
        snap_couch = self.detector._compute_posture(person_couch, [couch], ts)

        t0 = PersonTracker(tracker_id=0, state_entered_at=ts)
        t1 = PersonTracker(tracker_id=1, state_entered_at=ts)

        conf_floor = self.detector._compute_fall_confidence(snap_floor, t0)
        conf_couch = self.detector._compute_fall_confidence(snap_couch, t1)

        assert conf_couch < conf_floor, (
            f"Couch conf ({conf_couch:.2f}) should be less than floor ({conf_floor:.2f})"
        )

    def test_sitting_low_score(self):
        person = sitting_person()
        snap = self.detector._compute_posture(person, [], time.time())
        tracker = PersonTracker(tracker_id=0, state_entered_at=time.time())
        conf = self.detector._compute_fall_confidence(snap, tracker)
        assert conf < 0.4, f"Sitting person should have low confidence, got {conf:.2f}"

    def test_bending_moderate_score(self):
        person = bending_person()
        snap = self.detector._compute_posture(person, [], time.time())
        tracker = PersonTracker(tracker_id=0, state_entered_at=time.time())
        conf = self.detector._compute_fall_confidence(snap, tracker)
        # Bending might trigger some signals but shouldn't be high enough
        assert conf < 0.5, f"Bending person should have moderate confidence, got {conf:.2f}"


# ---------------------------------------------------------------------------
# TestStateMachine
# ---------------------------------------------------------------------------

class TestStateMachine:
    def setup_method(self):
        self.detector = FallDetector(
            confirmation_sec=5.0,
            recovery_sec=10.0,
            alert_cooldown_sec=120.0,
        )

    def test_momentary_squat_no_alert(self):
        """Brief dip below threshold should not trigger alert."""
        now = time.time()
        image_shape = (480, 640, 3)

        # Frame 1: person falls (high confidence)
        persons = [fallen_person()]
        alerts = self.detector.update(persons, [], image_shape)
        assert len(alerts) == 0  # Too early

        # Frame 2 (1 second later): person stands up
        with patch("fall_detector.time") as mock_time:
            mock_time.time.return_value = now + 1.0
            persons = [standing_person()]
            alerts = self.detector.update(persons, [], image_shape)
        assert len(alerts) == 0

    def test_sustained_fall_triggers_alert(self):
        """Fall maintained for confirmation period should trigger exactly one alert."""
        base_time = 1000.0
        image_shape = (480, 640, 3)
        alerts_total = []

        with patch("fall_detector.time") as mock_time:
            # Simulate 8 seconds of sustained fall (>5s confirmation)
            for i in range(9):  # 0 to 8 seconds, step 1s
                mock_time.time.return_value = base_time + i
                persons = [fallen_person()]
                alerts = self.detector.update(persons, [], image_shape)
                alerts_total.extend(alerts)

        assert len(alerts_total) == 1, f"Expected 1 alert, got {len(alerts_total)}"
        assert alerts_total[0].confidence >= 0.5

    def test_cooldown_prevents_repeat_alert(self):
        """After alert, same person shouldn't trigger again within cooldown."""
        base_time = 1000.0
        image_shape = (480, 640, 3)
        alerts_total = []

        # Use consistent center position so tracker matches across poses
        cx = 300

        with patch("fall_detector.time") as mock_time:
            # First fall -> alert
            for i in range(10):
                mock_time.time.return_value = base_time + i
                alerts = self.detector.update(
                    [fallen_person(cx=cx)], [], image_shape
                )
                alerts_total.extend(alerts)

            first_alert_count = len(alerts_total)
            assert first_alert_count == 1, (
                f"Expected 1 alert from first fall, got {first_alert_count}"
            )

            # Verify tracker exists and has cooldown set
            tracker = list(self.detector._trackers.values())[0]
            assert tracker.last_alert_time > 0

            # Second fall immediately (within cooldown 120s) — same tracker
            # Re-use fallen pose at same position so tracker matches
            for i in range(10):
                mock_time.time.return_value = base_time + 15 + i
                alerts = self.detector.update(
                    [fallen_person(cx=cx)], [], image_shape
                )
                alerts_total.extend(alerts)

        assert len(alerts_total) == 1, f"Expected 1 alert (cooldown), got {len(alerts_total)}"


# ---------------------------------------------------------------------------
# TestFurnitureDiscrimination
# ---------------------------------------------------------------------------

class TestFurnitureDiscrimination:
    def setup_method(self):
        self.detector = FallDetector(confirmation_sec=2.0)

    def test_couch_lying_no_alert(self):
        """Person lying on couch should NOT trigger fall alert."""
        base_time = 1000.0
        image_shape = (480, 640, 3)
        couch = _couch_bbox()
        alerts_total = []

        with patch("fall_detector.time") as mock_time:
            for i in range(10):
                mock_time.time.return_value = base_time + i
                persons = [lying_on_couch()]
                alerts = self.detector.update(persons, [couch], image_shape)
                alerts_total.extend(alerts)

        assert len(alerts_total) == 0, (
            f"Couch nap should not trigger alert, got {len(alerts_total)}"
        )

    def test_floor_lying_triggers_alert(self):
        """Person lying on floor (no furniture) SHOULD trigger alert."""
        base_time = 1000.0
        image_shape = (480, 640, 3)
        alerts_total = []

        with patch("fall_detector.time") as mock_time:
            for i in range(10):
                mock_time.time.return_value = base_time + i
                persons = [fallen_person()]
                alerts = self.detector.update(persons, [], image_shape)
                alerts_total.extend(alerts)

        assert len(alerts_total) >= 1, "Floor fall should trigger alert"


# ---------------------------------------------------------------------------
# TestComputePosture
# ---------------------------------------------------------------------------

class TestComputePosture:
    def setup_method(self):
        self.detector = FallDetector()

    def test_valid_person(self):
        person = standing_person()
        snap = self.detector._compute_posture(person, [], time.time())
        assert snap is not None
        assert snap.torso_angle is not None
        assert snap.torso_angle < 15.0

    def test_missing_bbox_returns_none(self):
        snap = self.detector._compute_posture(
            {"keypoints": [], "keypoint_conf": []}, [], time.time()
        )
        assert snap is None

    def test_furniture_detection(self):
        person = lying_on_couch()
        couch = _couch_bbox()
        snap = self.detector._compute_posture(person, [couch], time.time())
        assert snap is not None
        assert snap.hip_in_furniture is True
        assert snap.furniture_iou > 0.0


# ---------------------------------------------------------------------------
# TestTransitionDetection
# ---------------------------------------------------------------------------

class TestTransitionDetection:
    def setup_method(self):
        self.detector = FallDetector()

    def test_rapid_transition(self):
        """Rapid angle change within window should return high value."""
        now = time.time()
        tracker = PersonTracker(
            tracker_id=0,
            prev_torso_angle=5.0,   # Was upright
            prev_angle_time=now - 0.5,  # 0.5s ago
        )
        snap = PostureSnapshot(
            person_bbox=[0, 0, 100, 100],
            torso_angle=80.0,  # Now horizontal
            head_below_hips=True,
            bbox_aspect_ratio=0.5,
            ankle_shoulder_ratio=1.0,
            hip_midpoint=[50, 50],
            hip_in_furniture=False,
            furniture_iou=0.0,
            timestamp=now,
        )
        t = self.detector._detect_transition(tracker, snap)
        assert t > 0.5, f"Rapid transition should score high, got {t:.2f}"

    def test_no_transition_slow_change(self):
        """Gradual change outside window should return 0."""
        now = time.time()
        tracker = PersonTracker(
            tracker_id=0,
            prev_torso_angle=5.0,
            prev_angle_time=now - 5.0,  # 5s ago (outside 1s window)
        )
        snap = PostureSnapshot(
            person_bbox=[0, 0, 100, 100],
            torso_angle=80.0,
            head_below_hips=True,
            bbox_aspect_ratio=0.5,
            ankle_shoulder_ratio=1.0,
            hip_midpoint=[50, 50],
            hip_in_furniture=False,
            furniture_iou=0.0,
            timestamp=now,
        )
        t = self.detector._detect_transition(tracker, snap)
        assert t == 0.0


# ---------------------------------------------------------------------------
# TestUpdate (integration)
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_empty_input(self):
        detector = FallDetector()
        alerts = detector.update([], [], (480, 640, 3))
        assert alerts == []

    def test_single_standing_no_alert(self):
        detector = FallDetector()
        alerts = detector.update([standing_person()], [], (480, 640, 3))
        assert alerts == []

    def test_tracker_matching(self):
        """Same person in consecutive frames should reuse tracker."""
        detector = FallDetector()
        # Frame 1
        detector.update([standing_person(cx=300)], [], (480, 640, 3))
        n1 = len(detector._trackers)
        # Frame 2 (same position)
        detector.update([standing_person(cx=305)], [], (480, 640, 3))
        n2 = len(detector._trackers)
        assert n2 == n1, "Same person should reuse tracker"

    def test_multiple_persons(self):
        """Multiple persons should create separate trackers."""
        detector = FallDetector()
        persons = [standing_person(cx=100), standing_person(cx=500)]
        detector.update(persons, [], (480, 640, 3))
        assert len(detector._trackers) == 2


# ---------------------------------------------------------------------------
# TestHipMidpoint
# ---------------------------------------------------------------------------

class TestHipMidpoint:
    def test_valid(self):
        person = standing_person(cx=300, cy_top=50)
        hip = FallDetector._hip_midpoint(
            person["keypoints"], person["keypoint_conf"]
        )
        assert hip is not None
        assert abs(hip[0] - 300.0) < 1.0  # Near center x

    def test_missing_returns_none(self):
        kp = [[0.0, 0.0] for _ in range(17)]
        conf = [0.0] * 17
        assert FallDetector._hip_midpoint(kp, conf) is None
