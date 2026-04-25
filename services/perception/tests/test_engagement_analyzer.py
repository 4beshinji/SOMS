"""Unit tests for engagement_analyzer (pure pose-keypoint logic)."""
import numpy as np
import pytest

from engagement_analyzer import (
    EngagementAnalyzer,
    derive_frame_signals,
    KP_NOSE,
    KP_L_EYE,
    KP_R_EYE,
    KP_L_EAR,
    KP_R_EAR,
    KP_L_SHOULDER,
    KP_R_SHOULDER,
    KP_L_WRIST,
    KP_R_WRIST,
    KP_L_HIP,
    KP_R_HIP,
)


def _person(kpts_dict, bbox=None, conf_default=0.9):
    """Build a person dict from {idx: (x, y)} pairs (filling in zeros for missing)."""
    kpts = np.zeros((17, 2), dtype=np.float32)
    confs = np.zeros((17,), dtype=np.float32)
    for idx, (x, y) in kpts_dict.items():
        kpts[idx] = [x, y]
        confs[idx] = conf_default
    return {
        "bbox": bbox if bbox is not None else [200, 100, 400, 500],
        "confidence": 0.9,
        "keypoints": kpts,
        "keypoint_conf": confs,
    }


IMG_SHAPE = (480, 640)  # (h, w)


class TestDeriveFrameSignals:
    def test_facing_camera_keypoints(self):
        """Both ears + centered nose => orientation 'facing'."""
        person = _person({
            KP_NOSE: (320, 200),
            KP_L_EYE: (305, 195),
            KP_R_EYE: (335, 195),
            KP_L_EAR: (290, 200),
            KP_R_EAR: (350, 200),
            KP_L_SHOULDER: (280, 280),
            KP_R_SHOULDER: (360, 280),
            KP_L_HIP: (290, 420),
            KP_R_HIP: (350, 420),
        })
        sig = derive_frame_signals(person, IMG_SHAPE)
        assert sig.face_orientation == "facing"
        assert sig.attention == "looking_at"
        assert sig.posture == "upright"
        assert sig.face_visible is True

    def test_looking_left(self):
        """Right ear missing + nose far left of ear-mid => 'left'."""
        person = _person({
            KP_NOSE: (270, 200),
            KP_L_EYE: (260, 195),
            KP_L_EAR: (300, 200),
            # No right ear
            KP_L_SHOULDER: (280, 280),
            KP_R_SHOULDER: (360, 280),
        })
        sig = derive_frame_signals(person, IMG_SHAPE)
        assert sig.face_orientation == "left"
        assert sig.attention == "not_looking"

    def test_looking_right(self):
        person = _person({
            KP_NOSE: (380, 200),
            KP_R_EYE: (390, 195),
            KP_R_EAR: (350, 200),
            KP_L_SHOULDER: (280, 280),
            KP_R_SHOULDER: (360, 280),
        })
        sig = derive_frame_signals(person, IMG_SHAPE)
        assert sig.face_orientation == "right"

    def test_looking_down(self):
        """Nose well below eye-line relative to torso => orientation 'down'."""
        person = _person({
            KP_NOSE: (320, 260),
            KP_L_EYE: (305, 200),
            KP_R_EYE: (335, 200),
            KP_L_EAR: (290, 200),
            KP_R_EAR: (350, 200),
            KP_L_SHOULDER: (280, 320),
            KP_R_SHOULDER: (360, 320),
        })
        sig = derive_frame_signals(person, IMG_SHAPE)
        assert sig.face_orientation == "down"
        assert sig.head_pitch_hint > 0.45

    def test_back_of_head(self):
        """No facial keypoints => orientation 'away'."""
        person = _person({
            KP_L_SHOULDER: (280, 280),
            KP_R_SHOULDER: (360, 280),
        })
        sig = derive_frame_signals(person, IMG_SHAPE)
        assert sig.face_orientation == "away"
        assert sig.face_visible is False

    def test_hand_raised(self):
        """Wrist above shoulder line => posture 'hand_raised'."""
        person = _person({
            KP_NOSE: (320, 200),
            KP_L_EAR: (290, 200),
            KP_R_EAR: (350, 200),
            KP_L_SHOULDER: (280, 280),
            KP_R_SHOULDER: (360, 280),
            KP_L_WRIST: (270, 150),  # well above shoulder
            KP_L_HIP: (290, 420),
            KP_R_HIP: (350, 420),
        })
        sig = derive_frame_signals(person, IMG_SHAPE)
        assert sig.posture == "hand_raised"
        assert sig.gesture == "hand_raised"

    def test_attention_off_center(self):
        """Facing but bbox at extreme edge => not_looking."""
        person = _person(
            {
                KP_NOSE: (50, 200),
                KP_L_EYE: (40, 195),
                KP_R_EYE: (60, 195),
                KP_L_EAR: (30, 200),
                KP_R_EAR: (75, 200),
                KP_L_SHOULDER: (20, 280),
                KP_R_SHOULDER: (90, 280),
                KP_L_HIP: (25, 420),
                KP_R_HIP: (85, 420),
            },
            bbox=[10, 100, 110, 500],
        )
        sig = derive_frame_signals(person, IMG_SHAPE)
        assert sig.face_orientation == "facing"
        # bbox center at x=60, image w=640, offset = (60-320)/320 = ~0.81 > 0.6
        assert sig.attention == "not_looking"


class TestEngagementAnalyzer:
    def test_entered_view_event_on_first_frame(self):
        analyzer = EngagementAnalyzer()
        person = _person({
            KP_NOSE: (320, 200),
            KP_L_EYE: (305, 195),
            KP_R_EYE: (335, 195),
            KP_L_EAR: (290, 200),
            KP_R_EAR: (350, 200),
            KP_L_SHOULDER: (280, 280),
            KP_R_SHOULDER: (360, 280),
            KP_L_HIP: (290, 420),
            KP_R_HIP: (350, 420),
        })
        events, snaps = analyzer.analyze([person], IMG_SHAPE, now=1000.0)
        types = {e["event"] for e in events}
        assert "entered_view" in types
        assert len(snaps) == 1
        assert snaps[0]["face_orientation"] == "facing"

    def test_looked_at_then_looked_away(self):
        analyzer = EngagementAnalyzer()
        looking_at = _person({
            KP_NOSE: (320, 200),
            KP_L_EYE: (305, 195),
            KP_R_EYE: (335, 195),
            KP_L_EAR: (290, 200),
            KP_R_EAR: (350, 200),
            KP_L_SHOULDER: (280, 280),
            KP_R_SHOULDER: (360, 280),
            KP_L_HIP: (290, 420),
            KP_R_HIP: (350, 420),
        })
        # First frame: enters + looking_at
        analyzer.analyze([looking_at], IMG_SHAPE, now=1000.0)

        # Second frame: head turned right (loses left ear, nose far from ear-mid)
        looking_away = _person({
            KP_NOSE: (380, 200),
            KP_R_EAR: (350, 200),
            KP_L_SHOULDER: (280, 280),
            KP_R_SHOULDER: (360, 280),
            KP_L_HIP: (290, 420),
            KP_R_HIP: (350, 420),
        })
        events, _ = analyzer.analyze([looking_away], IMG_SHAPE, now=1001.0)
        assert any(e["event"] == "looked_away" for e in events)

    def test_left_view_after_disappearing(self):
        analyzer = EngagementAnalyzer()
        person = _person({
            KP_NOSE: (320, 200),
            KP_L_EAR: (290, 200),
            KP_R_EAR: (350, 200),
            KP_L_SHOULDER: (280, 280),
            KP_R_SHOULDER: (360, 280),
        })
        analyzer.analyze([person], IMG_SHAPE, now=1000.0)
        events, _ = analyzer.analyze([], IMG_SHAPE, now=1010.0)  # 10s gap
        assert any(e["event"] == "left_view" for e in events)

    def test_looked_at_cooldown_suppresses_repeats(self):
        """Repeated looked_at within cooldown window must not re-fire."""
        analyzer = EngagementAnalyzer()
        looking_at = _person({
            KP_NOSE: (320, 200),
            KP_L_EAR: (290, 200),
            KP_R_EAR: (350, 200),
            KP_L_SHOULDER: (280, 280),
            KP_R_SHOULDER: (360, 280),
            KP_L_HIP: (290, 420),
            KP_R_HIP: (350, 420),
        })
        looking_away = _person({
            KP_NOSE: (380, 200),
            KP_R_EAR: (350, 200),
            KP_L_SHOULDER: (280, 280),
            KP_R_SHOULDER: (360, 280),
            KP_L_HIP: (290, 420),
            KP_R_HIP: (350, 420),
        })
        # Frame 1: enters + (no looked_at yet because no prior signals)
        analyzer.analyze([looking_at], IMG_SHAPE, now=1000.0)
        # Frame 2: away — gives looked_away
        analyzer.analyze([looking_away], IMG_SHAPE, now=1001.0)
        # Frame 3: back to looking_at — fires looked_at (first time)
        ev3, _ = analyzer.analyze([looking_at], IMG_SHAPE, now=1002.0)
        # Frame 4: away again
        analyzer.analyze([looking_away], IMG_SHAPE, now=1003.0)
        # Frame 5: looking_at again, only 4s after first looked_at — cooldown 30s
        ev5, _ = analyzer.analyze([looking_at], IMG_SHAPE, now=1006.0)
        assert any(e["event"] == "looked_at" for e in ev3)
        assert not any(e["event"] == "looked_at" for e in ev5)

    def test_wave_detection(self):
        """Wrist crossing above-shoulder line repeatedly => waved event."""
        analyzer = EngagementAnalyzer()
        # Build a sequence where left wrist alternates above/below shoulder.
        wrist_positions = [
            150,  # above
            350,  # below
            150,
            350,
            150,
        ]
        all_events = []
        for i, wy in enumerate(wrist_positions):
            person = _person({
                KP_NOSE: (320, 200),
                KP_L_EAR: (290, 200),
                KP_R_EAR: (350, 200),
                KP_L_SHOULDER: (280, 280),
                KP_R_SHOULDER: (360, 280),
                KP_L_HIP: (290, 420),
                KP_R_HIP: (350, 420),
                KP_L_WRIST: (250, wy),
            })
            events, _ = analyzer.analyze([person], IMG_SHAPE, now=1000.0 + i * 0.3)
            all_events.extend(events)
        types = {e["event"] for e in all_events}
        assert "waved" in types
