"""
FallDetector — geometric heuristic fall detection with furniture context.

Uses YOLO object detections (chair/couch/bed) and YOLO-Pose keypoints to
distinguish genuine falls from napping on furniture. No ML training required.

State machine per tracked person:
  NORMAL -> SUSPICIOUS (conf >= threshold, held 5s) -> FALL_CONFIRMED -> ALERT_SENT
  Any state -> RECOVERING (conf < threshold) -> NORMAL (held 10s)
"""

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# COCO keypoint indices
_NOSE = 0
_L_SHOULDER, _R_SHOULDER = 5, 6
_L_HIP, _R_HIP = 11, 12
_L_ANKLE, _R_ANKLE = 15, 16

# Furniture YOLO class names to consider
_FURNITURE_CLASSES = {"chair", "couch", "bed", "sofa", "bench"}

# Confidence weight constants
_W_TORSO_ANGLE = 0.35
_W_HEAD_BELOW = 0.25
_W_BBOX_RATIO = 0.15
_W_TRANSITION = 0.15
_W_ANKLE_RATIO = 0.10

# Furniture penalty constants
_PENALTY_HIP_IN_FURNITURE = 0.40
_PENALTY_FURNITURE_IOU = 0.25

# Keypoint confidence threshold
_KPT_CONF = 0.3


class PersonState(Enum):
    NORMAL = "normal"
    SUSPICIOUS = "suspicious"
    FALL_CONFIRMED = "fall_confirmed"
    ALERT_SENT = "alert_sent"
    RECOVERING = "recovering"


@dataclass
class PostureSnapshot:
    """Single-frame posture analysis result for one person."""
    person_bbox: List[float]       # [x1, y1, x2, y2]
    torso_angle: Optional[float]   # degrees, 0=upright, 90=horizontal
    head_below_hips: bool
    bbox_aspect_ratio: float       # height / width
    ankle_shoulder_ratio: float    # ankle spread / shoulder width
    hip_midpoint: Optional[List[float]]  # [x, y] or None
    hip_in_furniture: bool
    furniture_iou: float
    timestamp: float


@dataclass
class PersonTracker:
    """Tracks fall detection state for a single person across frames."""
    tracker_id: int
    state: PersonState = PersonState.NORMAL
    last_bbox: List[float] = field(default_factory=list)
    state_entered_at: float = 0.0
    last_alert_time: float = 0.0
    confidence: float = 0.0
    # History for transition detection
    prev_torso_angle: Optional[float] = None
    prev_angle_time: float = 0.0


@dataclass
class FallAlert:
    """Alert emitted when a fall is confirmed."""
    tracker_id: int
    confidence: float
    duration_sec: float
    bbox: List[float]
    zone: str = ""


class FallDetector:
    """Geometric heuristic fall detection with furniture context."""

    def __init__(
        self,
        torso_angle_threshold: float = 60.0,
        fall_confidence_threshold: float = 0.5,
        confirmation_sec: float = 5.0,
        recovery_sec: float = 10.0,
        alert_cooldown_sec: float = 120.0,
        furniture_iou_threshold: float = 0.15,
        transition_window_sec: float = 1.0,
    ):
        self.torso_angle_threshold = torso_angle_threshold
        self.fall_confidence_threshold = fall_confidence_threshold
        self.confirmation_sec = confirmation_sec
        self.recovery_sec = recovery_sec
        self.alert_cooldown_sec = alert_cooldown_sec
        self.furniture_iou_threshold = furniture_iou_threshold
        self.transition_window_sec = transition_window_sec

        self._trackers: Dict[int, PersonTracker] = {}
        self._next_id: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        persons_pose: List[dict],
        all_detections: List[dict],
        image_shape: Tuple[int, ...],
    ) -> List[FallAlert]:
        """
        Process one frame of detections and return any fall alerts.

        Args:
            persons_pose: List of pose dicts from PoseEstimator
                          (each has "bbox", "keypoints", "keypoint_conf")
            all_detections: List of detection dicts from YOLOInference
                           (each has "class", "bbox", "confidence")
            image_shape: (height, width, ...) of the input image

        Returns:
            List of FallAlert for newly confirmed falls.
        """
        now = time.time()

        # Extract furniture bboxes
        furniture = [
            d for d in all_detections
            if d.get("class", "").lower() in _FURNITURE_CLASSES
        ]

        # Compute posture snapshot for each person
        snapshots = []
        for person in persons_pose:
            snap = self._compute_posture(person, furniture, now)
            if snap is not None:
                snapshots.append(snap)

        # Match snapshots to existing trackers and create new ones
        self._match_and_update_trackers(snapshots, now)

        # Evaluate state machine for each tracker
        alerts = []
        for tracker in self._trackers.values():
            alert = self._evaluate_state(tracker, now)
            if alert is not None:
                alerts.append(alert)

        # Prune stale trackers (no update for 30s)
        stale = [
            tid for tid, t in self._trackers.items()
            if now - t.state_entered_at > 30.0
            and t.state == PersonState.NORMAL
            and t.confidence == 0.0
        ]
        for tid in stale:
            del self._trackers[tid]

        return alerts

    # ------------------------------------------------------------------
    # Geometry helpers (static / class methods)
    # ------------------------------------------------------------------

    @staticmethod
    def _torso_angle(kp: List[List[float]], conf: List[float]) -> Optional[float]:
        """
        Compute torso angle from vertical (0=upright, 90=horizontal).
        Uses shoulder midpoint -> hip midpoint vector.
        """
        if (conf[_L_SHOULDER] < _KPT_CONF or conf[_R_SHOULDER] < _KPT_CONF
                or conf[_L_HIP] < _KPT_CONF or conf[_R_HIP] < _KPT_CONF):
            return None

        shoulder_mid = [
            (kp[_L_SHOULDER][0] + kp[_R_SHOULDER][0]) / 2,
            (kp[_L_SHOULDER][1] + kp[_R_SHOULDER][1]) / 2,
        ]
        hip_mid = [
            (kp[_L_HIP][0] + kp[_R_HIP][0]) / 2,
            (kp[_L_HIP][1] + kp[_R_HIP][1]) / 2,
        ]

        # Vector from shoulder to hip (image coords: y increases downward)
        dx = hip_mid[0] - shoulder_mid[0]
        dy = hip_mid[1] - shoulder_mid[1]

        # Angle from vertical (downward = 0 degrees)
        # atan2 of horizontal component vs vertical component
        angle = math.degrees(math.atan2(abs(dx), abs(dy)))
        return angle

    @staticmethod
    def _head_below_hips(kp: List[List[float]], conf: List[float]) -> bool:
        """Check if nose is below hip midpoint (image y-axis: larger = lower)."""
        if conf[_NOSE] < _KPT_CONF:
            return False
        if conf[_L_HIP] < _KPT_CONF or conf[_R_HIP] < _KPT_CONF:
            return False

        nose_y = kp[_NOSE][1]
        hip_mid_y = (kp[_L_HIP][1] + kp[_R_HIP][1]) / 2
        return nose_y > hip_mid_y

    @staticmethod
    def _ankle_shoulder_ratio(kp: List[List[float]], conf: List[float]) -> float:
        """
        Ratio of ankle spread to shoulder width.
        Normal ~1.0, fallen > 1.5.
        Returns 1.0 if keypoints not visible.
        """
        if (conf[_L_SHOULDER] < _KPT_CONF or conf[_R_SHOULDER] < _KPT_CONF
                or conf[_L_ANKLE] < _KPT_CONF or conf[_R_ANKLE] < _KPT_CONF):
            return 1.0

        shoulder_w = abs(kp[_L_SHOULDER][0] - kp[_R_SHOULDER][0])
        ankle_w = abs(kp[_L_ANKLE][0] - kp[_R_ANKLE][0])

        if shoulder_w < 1e-6:
            return 1.0
        return ankle_w / shoulder_w

    @staticmethod
    def _hip_midpoint(kp: List[List[float]], conf: List[float]) -> Optional[List[float]]:
        """Return hip midpoint [x, y] or None."""
        if conf[_L_HIP] < _KPT_CONF or conf[_R_HIP] < _KPT_CONF:
            return None
        return [
            (kp[_L_HIP][0] + kp[_R_HIP][0]) / 2,
            (kp[_L_HIP][1] + kp[_R_HIP][1]) / 2,
        ]

    @staticmethod
    def _bbox_iou(bbox_a: List[float], bbox_b: List[float]) -> float:
        """Compute IoU between two [x1, y1, x2, y2] bounding boxes."""
        x1 = max(bbox_a[0], bbox_b[0])
        y1 = max(bbox_a[1], bbox_b[1])
        x2 = min(bbox_a[2], bbox_b[2])
        y2 = min(bbox_a[3], bbox_b[3])

        inter = max(0, x2 - x1) * max(0, y2 - y1)
        if inter == 0:
            return 0.0

        area_a = (bbox_a[2] - bbox_a[0]) * (bbox_a[3] - bbox_a[1])
        area_b = (bbox_b[2] - bbox_b[0]) * (bbox_b[3] - bbox_b[1])
        union = area_a + area_b - inter

        if union <= 0:
            return 0.0
        return inter / union

    @staticmethod
    def _point_in_bbox(point: List[float], bbox: List[float]) -> bool:
        """Check if [x, y] point is inside [x1, y1, x2, y2] bbox."""
        return (bbox[0] <= point[0] <= bbox[2]
                and bbox[1] <= point[1] <= bbox[3])

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def _compute_posture(
        self,
        person: dict,
        furniture: List[dict],
        ts: float,
    ) -> Optional[PostureSnapshot]:
        """Analyze a single person's posture relative to furniture."""
        bbox = person.get("bbox")
        kp = person.get("keypoints")
        kp_conf = person.get("keypoint_conf")

        if bbox is None or kp is None or kp_conf is None:
            return None
        if len(kp) < 17 or len(kp_conf) < 17:
            return None

        # Bbox aspect ratio (height / width)
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        aspect = bh / bw if bw > 1e-6 else 1.0

        # Geometric metrics
        torso = self._torso_angle(kp, kp_conf)
        head_below = self._head_below_hips(kp, kp_conf)
        ankle_ratio = self._ankle_shoulder_ratio(kp, kp_conf)
        hip_mid = self._hip_midpoint(kp, kp_conf)

        # Furniture context
        hip_in_furn = False
        max_iou = 0.0
        for furn in furniture:
            furn_bbox = furn.get("bbox", [])
            if len(furn_bbox) < 4:
                continue
            iou = self._bbox_iou(bbox, furn_bbox)
            if iou > max_iou:
                max_iou = iou
            if hip_mid and self._point_in_bbox(hip_mid, furn_bbox):
                hip_in_furn = True

        return PostureSnapshot(
            person_bbox=bbox,
            torso_angle=torso,
            head_below_hips=head_below,
            bbox_aspect_ratio=aspect,
            ankle_shoulder_ratio=ankle_ratio,
            hip_midpoint=hip_mid,
            hip_in_furniture=hip_in_furn,
            furniture_iou=max_iou,
            timestamp=ts,
        )

    def _compute_fall_confidence(
        self,
        snap: PostureSnapshot,
        tracker: PersonTracker,
    ) -> float:
        """Compute fall confidence score (0.0 - 1.0) from posture snapshot."""
        score = 0.0

        # Torso angle component
        if snap.torso_angle is not None:
            if snap.torso_angle >= self.torso_angle_threshold:
                # Scale linearly from threshold to 90 degrees
                t = min(1.0, (snap.torso_angle - self.torso_angle_threshold)
                        / (90.0 - self.torso_angle_threshold))
                score += _W_TORSO_ANGLE * t
            # Below threshold contributes nothing

        # Head below hips
        if snap.head_below_hips:
            score += _W_HEAD_BELOW

        # Bbox aspect ratio (< 1.0 means wider than tall = lying down)
        if snap.bbox_aspect_ratio < 1.0:
            t = 1.0 - snap.bbox_aspect_ratio  # 0 at ratio=1, 1 at ratio=0
            score += _W_BBOX_RATIO * min(1.0, t)

        # Rapid transition
        transition = self._detect_transition(tracker, snap)
        score += _W_TRANSITION * transition

        # Ankle-shoulder ratio abnormality
        if snap.ankle_shoulder_ratio > 1.5:
            t = min(1.0, (snap.ankle_shoulder_ratio - 1.5) / 1.5)
            score += _W_ANKLE_RATIO * t

        # --- Negative signals (furniture context) ---
        if snap.hip_in_furniture:
            score -= _PENALTY_HIP_IN_FURNITURE

        if snap.furniture_iou > self.furniture_iou_threshold:
            # Scale penalty with IoU strength
            t = min(1.0, snap.furniture_iou / 0.5)
            score -= _PENALTY_FURNITURE_IOU * t

        return max(0.0, min(1.0, score))

    def _detect_transition(
        self,
        tracker: PersonTracker,
        current: PostureSnapshot,
    ) -> float:
        """
        Detect rapid posture transition (0.0 - 1.0).
        Returns 1.0 if torso angle changed by >= 60 degrees within window.
        """
        if tracker.prev_torso_angle is None or current.torso_angle is None:
            return 0.0

        dt = current.timestamp - tracker.prev_angle_time
        if dt <= 0 or dt > self.transition_window_sec:
            return 0.0

        angle_change = abs(current.torso_angle - tracker.prev_torso_angle)
        if angle_change >= 60.0:
            return min(1.0, angle_change / 90.0)
        return 0.0

    def _evaluate_state(
        self,
        tracker: PersonTracker,
        now: float,
    ) -> Optional[FallAlert]:
        """Evaluate state machine for a tracker. Returns alert if newly confirmed."""
        conf = tracker.confidence
        threshold = self.fall_confidence_threshold

        if tracker.state == PersonState.NORMAL:
            if conf >= threshold:
                tracker.state = PersonState.SUSPICIOUS
                tracker.state_entered_at = now
        elif tracker.state == PersonState.SUSPICIOUS:
            if conf < threshold:
                tracker.state = PersonState.RECOVERING
                tracker.state_entered_at = now
            elif now - tracker.state_entered_at >= self.confirmation_sec:
                tracker.state = PersonState.FALL_CONFIRMED
                tracker.state_entered_at = now
        elif tracker.state == PersonState.FALL_CONFIRMED:
            # Emit alert once, then move to ALERT_SENT
            if (now - tracker.last_alert_time >= self.alert_cooldown_sec):
                tracker.state = PersonState.ALERT_SENT
                tracker.last_alert_time = now
                duration = now - tracker.state_entered_at + self.confirmation_sec
                return FallAlert(
                    tracker_id=tracker.tracker_id,
                    confidence=conf,
                    duration_sec=duration,
                    bbox=tracker.last_bbox,
                )
            else:
                tracker.state = PersonState.ALERT_SENT
                tracker.state_entered_at = now
        elif tracker.state == PersonState.ALERT_SENT:
            if conf < threshold:
                tracker.state = PersonState.RECOVERING
                tracker.state_entered_at = now
        elif tracker.state == PersonState.RECOVERING:
            if conf >= threshold:
                tracker.state = PersonState.SUSPICIOUS
                tracker.state_entered_at = now
            elif now - tracker.state_entered_at >= self.recovery_sec:
                tracker.state = PersonState.NORMAL
                tracker.state_entered_at = now

        return None

    def _match_and_update_trackers(
        self,
        snapshots: List[PostureSnapshot],
        now: float,
    ):
        """Match current snapshots to existing trackers by bbox proximity."""
        used_trackers = set()
        unmatched = []

        for snap in snapshots:
            best_tid = None
            best_dist = float("inf")
            snap_cx = (snap.person_bbox[0] + snap.person_bbox[2]) / 2
            snap_cy = (snap.person_bbox[1] + snap.person_bbox[3]) / 2

            for tid, tracker in self._trackers.items():
                if tid in used_trackers or not tracker.last_bbox:
                    continue
                tcx = (tracker.last_bbox[0] + tracker.last_bbox[2]) / 2
                tcy = (tracker.last_bbox[1] + tracker.last_bbox[3]) / 2
                dist = math.hypot(snap_cx - tcx, snap_cy - tcy)

                # Max match distance: half of bbox diagonal
                bw = snap.person_bbox[2] - snap.person_bbox[0]
                bh = snap.person_bbox[3] - snap.person_bbox[1]
                max_dist = math.hypot(bw, bh) / 2

                if dist < max_dist and dist < best_dist:
                    best_dist = dist
                    best_tid = tid

            if best_tid is not None:
                used_trackers.add(best_tid)
                tracker = self._trackers[best_tid]
                tracker.confidence = self._compute_fall_confidence(snap, tracker)
                # Update transition history
                tracker.prev_torso_angle = snap.torso_angle
                tracker.prev_angle_time = snap.timestamp
                tracker.last_bbox = snap.person_bbox
            else:
                unmatched.append(snap)

        # Create new trackers for unmatched persons
        for snap in unmatched:
            tid = self._next_id
            self._next_id += 1
            tracker = PersonTracker(
                tracker_id=tid,
                last_bbox=snap.person_bbox,
                state_entered_at=now,
            )
            tracker.confidence = self._compute_fall_confidence(snap, tracker)
            tracker.prev_torso_angle = snap.torso_angle
            tracker.prev_angle_time = snap.timestamp
            self._trackers[tid] = tracker
