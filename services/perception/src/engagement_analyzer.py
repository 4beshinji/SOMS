"""
Engagement Analyzer — derive face orientation, attention, posture, and
gesture cues from YOLO-Pose COCO17 keypoints.

Designed to run offline (no extra ML deps) so the system has *something*
to talk about even when only a USB webcam is available.

COCO17 keypoint indices (matches pose_estimator.KEYPOINT_NAMES):
  0 nose  1 left_eye  2 right_eye  3 left_ear  4 right_ear
  5 left_shoulder  6 right_shoulder
  7 left_elbow  8 right_elbow  9 left_wrist  10 right_wrist
  11 left_hip  12 right_hip
  13 left_knee 14 right_knee 15 left_ankle 16 right_ankle
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np


KP_NOSE = 0
KP_L_EYE = 1
KP_R_EYE = 2
KP_L_EAR = 3
KP_R_EAR = 4
KP_L_SHOULDER = 5
KP_R_SHOULDER = 6
KP_L_WRIST = 9
KP_R_WRIST = 10
KP_L_HIP = 11
KP_R_HIP = 12

# Minimum keypoint confidence to trust a single landmark.
KP_CONF_MIN = 0.35


@dataclass
class FrameSignals:
    """Per-frame, per-person derived signals (no temporal info)."""
    present: bool = False
    face_visible: bool = False
    face_orientation: str = "unknown"   # facing|left|right|down|up|away|unknown
    attention: str = "unknown"          # looking_at|not_looking|unknown
    posture: str = "unknown"            # upright|leaning_forward|slouched|hand_raised|unknown
    gesture: Optional[str] = None       # wave|hand_raised|None (frame-level — wave is detected over history)
    head_yaw_hint: float = 0.0          # -1 (left) .. +1 (right), 0 = facing
    head_pitch_hint: float = 0.0        # -1 (up) .. +1 (down)
    bbox_area_ratio: float = 0.0        # bbox area / image area
    mouth_open_hint: bool = False       # heuristic only — distance between nose & chin proxy


@dataclass
class _PersonHistory:
    """Tiny per-track history used to detect transitions."""
    last_signals: Optional[FrameSignals] = None
    wrist_y_history: Deque[Tuple[float, float, float]] = field(
        default_factory=lambda: deque(maxlen=12)
    )  # (timestamp, left_wrist_y, right_wrist_y) — None values stored as NaN
    last_event_times: Dict[str, float] = field(default_factory=dict)
    first_seen: float = 0.0


# Cooldown windows (sec) per event type to avoid the brain getting spammed.
_EVENT_COOLDOWN = {
    "entered_view": 60.0,
    "looked_at": 30.0,
    "looked_away": 60.0,
    "waved": 30.0,
    "hand_raised": 30.0,
    "leaned_in": 60.0,
    "head_down": 120.0,
    "left_view": 60.0,
}


def _kp(person: dict, idx: int) -> Optional[Tuple[float, float, float]]:
    """Return (x, y, conf) for a keypoint or None if not confident enough."""
    kpts = person.get("keypoints")
    confs = person.get("keypoint_conf")
    if kpts is None or confs is None or idx >= len(confs):
        return None
    c = float(confs[idx])
    if c < KP_CONF_MIN:
        return None
    x, y = float(kpts[idx][0]), float(kpts[idx][1])
    return x, y, c


def derive_frame_signals(person: dict, image_shape: Tuple[int, int]) -> FrameSignals:
    """Compute per-frame engagement signals for one person.

    Args:
        person: dict from PoseEstimator.estimate() with keypoints/keypoint_conf/bbox
        image_shape: (height, width) of the source frame
    """
    h, w = image_shape[0], image_shape[1]
    sig = FrameSignals(present=True)

    bbox = person.get("bbox")
    if bbox and w > 0 and h > 0:
        x1, y1, x2, y2 = bbox[:4]
        sig.bbox_area_ratio = max(0.0, (x2 - x1) * (y2 - y1)) / float(w * h)

    nose = _kp(person, KP_NOSE)
    l_eye = _kp(person, KP_L_EYE)
    r_eye = _kp(person, KP_R_EYE)
    l_ear = _kp(person, KP_L_EAR)
    r_ear = _kp(person, KP_R_EAR)
    l_sh = _kp(person, KP_L_SHOULDER)
    r_sh = _kp(person, KP_R_SHOULDER)
    l_wr = _kp(person, KP_L_WRIST)
    r_wr = _kp(person, KP_R_WRIST)

    sig.face_visible = nose is not None or (l_eye is not None and r_eye is not None)

    # ── Face orientation (yaw/pitch hints) ──
    yaw_hint = 0.0
    pitch_hint = 0.0
    orientation = "unknown"

    if nose and l_ear and r_ear:
        # Yaw: nose horizontal position relative to ear midpoint.
        ear_mid_x = (l_ear[0] + r_ear[0]) / 2.0
        ear_span = max(1.0, abs(l_ear[0] - r_ear[0]))
        yaw_hint = float(np.clip((nose[0] - ear_mid_x) / (ear_span / 2.0), -1.5, 1.5))
        if abs(yaw_hint) < 0.35:
            orientation = "facing"
        elif yaw_hint > 0:
            orientation = "right"
        else:
            orientation = "left"
    elif nose and (l_ear or r_ear):
        # Only one ear visible — strong yaw signal.
        orientation = "right" if l_ear is None else "left"
        yaw_hint = 1.0 if l_ear is None else -1.0
    elif (l_eye and r_eye) and not (l_ear or r_ear):
        # Eyes only — partial face on; treat as "facing" with low confidence.
        orientation = "facing"
    elif not nose and not l_eye and not r_eye:
        # Back of head / fully turned away.
        orientation = "away"

    # Pitch: nose vs eye/ear y-line. Nose well below eyes → looking down.
    eye_ys = [p[1] for p in (l_eye, r_eye) if p is not None]
    ear_ys = [p[1] for p in (l_ear, r_ear) if p is not None]
    ref_y_list = eye_ys or ear_ys
    if nose and ref_y_list and l_sh and r_sh:
        ref_y = sum(ref_y_list) / len(ref_y_list)
        shoulder_y = (l_sh[1] + r_sh[1]) / 2.0
        face_height = max(1.0, abs(shoulder_y - ref_y))
        pitch_hint = float(np.clip((nose[1] - ref_y) / face_height, -1.5, 1.5))
        if pitch_hint > 0.45 and orientation in ("facing", "unknown"):
            orientation = "down"
        elif pitch_hint < -0.4 and orientation in ("facing", "unknown"):
            orientation = "up"

    sig.face_orientation = orientation
    sig.head_yaw_hint = yaw_hint
    sig.head_pitch_hint = pitch_hint

    # ── Attention: facing-camera + bbox roughly central ──
    if orientation == "facing" and bbox and w > 0:
        bbox_cx = (bbox[0] + bbox[2]) / 2.0
        offset = abs(bbox_cx - w / 2.0) / (w / 2.0)
        sig.attention = "looking_at" if offset < 0.6 else "not_looking"
    elif orientation in ("left", "right", "down", "up", "away"):
        sig.attention = "not_looking"
    else:
        sig.attention = "unknown"

    # ── Posture ──
    posture = "unknown"
    if l_sh and r_sh:
        shoulder_y = (l_sh[1] + r_sh[1]) / 2.0
        l_hip = _kp(person, KP_L_HIP)
        r_hip = _kp(person, KP_R_HIP)
        if l_hip and r_hip:
            hip_y = (l_hip[1] + r_hip[1]) / 2.0
            torso_h = max(1.0, hip_y - shoulder_y)
            # Heuristic: if any wrist is above the shoulder line, hand is raised
            wrist_above = False
            for w_kp in (l_wr, r_wr):
                if w_kp and w_kp[1] < shoulder_y - torso_h * 0.15:
                    wrist_above = True
                    break
            if wrist_above:
                posture = "hand_raised"
            elif nose and (nose[1] - shoulder_y) > -torso_h * 0.1:
                # Nose at-or-below shoulder line → slumped/leaning forward
                posture = "leaning_forward"
            else:
                posture = "upright"
        else:
            # Without hips, fall back: check wrist above shoulder
            wrist_above = any(
                w_kp and w_kp[1] < shoulder_y for w_kp in (l_wr, r_wr)
            )
            posture = "hand_raised" if wrist_above else "upright"
    sig.posture = posture

    # Frame-level "gesture" — only hand_raised is detectable in 1 frame; wave needs history
    if posture == "hand_raised":
        sig.gesture = "hand_raised"

    # ── Mouth open heuristic (very weak) ──
    # Without facial landmarks beyond eyes/nose, all we can say is whether the
    # nose-to-shoulder distance is unusually large for a face-on person —
    # which roughly tracks an open jaw / yawn. Disabled when not facing.
    if orientation == "facing" and nose and l_sh and r_sh:
        shoulder_y = (l_sh[1] + r_sh[1]) / 2.0
        if (shoulder_y - nose[1]) > sig.bbox_area_ratio * h * 0.45:
            # Heuristic threshold; very rough — used only for offline patter,
            # not as a clinical signal.
            sig.mouth_open_hint = True

    return sig


def _track_key(person: dict) -> str:
    """Stable-ish key for a person across frames (no real tracker)."""
    if "track_id" in person and person["track_id"] is not None:
        return f"trk_{person['track_id']}"
    bbox = person.get("bbox") or [0, 0, 0, 0]
    cx = int((bbox[0] + bbox[2]) / 2 / 40)  # ~40px bucket
    cy = int((bbox[1] + bbox[3]) / 2 / 40)
    return f"box_{cx}_{cy}"


class EngagementAnalyzer:
    """Stateful analyzer that turns per-frame signals into MQTT-ready events."""

    def __init__(self, history_seconds: float = 4.0):
        self.history_seconds = history_seconds
        self._history: Dict[str, _PersonHistory] = {}

    def analyze(
        self,
        persons: List[dict],
        image_shape: Tuple[int, int],
        now: Optional[float] = None,
    ) -> Tuple[List[dict], List[dict]]:
        """Update internal state and return (events, snapshots).

        Each event is a dict like:
          {"event": "looked_at", "track_key": ..., "timestamp": ..., **details}
        Each snapshot is the per-person FrameSignals as a dict, including track_key.
        """
        now = now if now is not None else time.time()
        events: List[dict] = []
        snapshots: List[dict] = []

        seen_keys = set()
        for person in persons:
            key = _track_key(person)
            seen_keys.add(key)
            sig = derive_frame_signals(person, image_shape)
            hist = self._history.get(key)
            new_track = hist is None
            if hist is None:
                hist = _PersonHistory(first_seen=now)
                self._history[key] = hist

            # Update wrist history for wave detection.
            kpts = person.get("keypoints")
            confs = person.get("keypoint_conf")
            l_y = float("nan")
            r_y = float("nan")
            if kpts is not None and confs is not None:
                if len(confs) > KP_L_WRIST and float(confs[KP_L_WRIST]) >= KP_CONF_MIN:
                    l_y = float(kpts[KP_L_WRIST][1])
                if len(confs) > KP_R_WRIST and float(confs[KP_R_WRIST]) >= KP_CONF_MIN:
                    r_y = float(kpts[KP_R_WRIST][1])
            hist.wrist_y_history.append((now, l_y, r_y))

            # Compose snapshot
            snap = {
                "track_key": key,
                "present": sig.present,
                "face_visible": sig.face_visible,
                "face_orientation": sig.face_orientation,
                "attention": sig.attention,
                "posture": sig.posture,
                "head_yaw_hint": round(sig.head_yaw_hint, 3),
                "head_pitch_hint": round(sig.head_pitch_hint, 3),
                "bbox_area_ratio": round(sig.bbox_area_ratio, 4),
                "gesture": sig.gesture,
                "mouth_open_hint": sig.mouth_open_hint,
            }
            snapshots.append(snap)

            # ── Event derivation ──
            prev = hist.last_signals
            if new_track:
                self._emit(events, hist, "entered_view", now, key, snap)

            if prev is not None:
                # Attention transitions
                if prev.attention != "looking_at" and sig.attention == "looking_at":
                    self._emit(events, hist, "looked_at", now, key, snap)
                if prev.attention == "looking_at" and sig.attention == "not_looking":
                    self._emit(events, hist, "looked_away", now, key, snap)
                # Head down transition (sleepy / discouraged proxy)
                if prev.face_orientation != "down" and sig.face_orientation == "down":
                    self._emit(events, hist, "head_down", now, key, snap)
                # Lean-in: bbox area grew significantly while facing camera
                if (
                    sig.face_orientation == "facing"
                    and prev.bbox_area_ratio > 0
                    and sig.bbox_area_ratio > prev.bbox_area_ratio * 1.4
                    and sig.bbox_area_ratio > 0.18
                ):
                    self._emit(events, hist, "leaned_in", now, key, snap)
                # Hand raised transition
                if prev.posture != "hand_raised" and sig.posture == "hand_raised":
                    self._emit(events, hist, "hand_raised", now, key, snap)

            # Wave detection — wrist crosses above shoulder line repeatedly
            if self._detect_wave(hist, person, now):
                self._emit(events, hist, "waved", now, key, snap)

            hist.last_signals = sig

        # Detect "left_view" for tracks we haven't seen this frame for >5s
        stale_keys = []
        for key, hist in self._history.items():
            if key in seen_keys:
                continue
            if hist.last_signals is None:
                continue
            # Use the most recent wrist history timestamp as last-seen proxy
            if hist.wrist_y_history:
                last_seen_ts = hist.wrist_y_history[-1][0]
            else:
                last_seen_ts = hist.first_seen
            if now - last_seen_ts > 5.0:
                self._emit(events, hist, "left_view", now, key, {"track_key": key})
                stale_keys.append(key)

        for key in stale_keys:
            self._history.pop(key, None)

        return events, snapshots

    def _emit(self, events, hist, event_type, now, key, snap):
        last = hist.last_event_times.get(event_type, 0.0)
        cooldown = _EVENT_COOLDOWN.get(event_type, 30.0)
        if now - last < cooldown:
            return
        hist.last_event_times[event_type] = now
        events.append({
            "event": event_type,
            "track_key": key,
            "timestamp": now,
            **{k: v for k, v in snap.items() if k != "track_key"},
        })

    def _detect_wave(self, hist: _PersonHistory, person: dict, now: float) -> bool:
        """Wave = wrist above shoulder line + crossing midline ≥2 times in window."""
        l_sh = _kp(person, KP_L_SHOULDER)
        r_sh = _kp(person, KP_R_SHOULDER)
        if not l_sh and not r_sh:
            return False
        shoulder_y = (
            (l_sh[1] + r_sh[1]) / 2.0 if l_sh and r_sh else (l_sh or r_sh)[1]
        )

        # Look at most recent ~2 seconds of wrist history.
        recent = [(t, ly, ry) for (t, ly, ry) in hist.wrist_y_history if now - t <= 2.0]
        if len(recent) < 4:
            return False

        # Count above-shoulder crossings on either wrist.
        def crossings(values):
            above = [v < shoulder_y for v in values if v == v]  # NaN-aware
            if len(above) < 4:
                return 0
            return sum(1 for a, b in zip(above, above[1:]) if a != b)

        l_vals = [ly for (_, ly, _) in recent]
        r_vals = [ry for (_, _, ry) in recent]
        above_any = any(v == v and v < shoulder_y for v in l_vals + r_vals)
        return above_any and (crossings(l_vals) + crossings(r_vals)) >= 2
