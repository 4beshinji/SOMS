"""Crime Coefficient — per-person threat score aggregated across VAD layers.

Combines anomaly signals from three VAD detectors + trajectory/temporal
analysis into a single EMA-smoothed "crime coefficient" per global person ID.

Score range: 0-300 (inspired by Psycho-Pass)
  0-100: Normal (clear)
  100-200: Latent criminal (warning)
  200-300: Enforcement target (critical)

Each sub-score is normalized to 0-100 and weighted.
"""
from __future__ import annotations

import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# Coefficient weights (sum to 1.0)
W_POSE = 0.25       # STG-NF pose anomaly
W_SCENE = 0.15      # AED-MAE scene reconstruction
W_ATTRIBUTE = 0.20   # AI-VAD velocity + appearance + pose
W_TRAJECTORY = 0.20  # Path anomaly (loitering, restricted zones)
W_TEMPORAL = 0.10    # Unusual time-of-day presence
W_SOCIAL = 0.10      # Proximity pattern anomaly

# Severity thresholds
CLEAR_THRESHOLD = 100
WARNING_THRESHOLD = 200
CRITICAL_THRESHOLD = 250


@dataclass
class TrajectoryPoint:
    timestamp: float
    floor_x: float
    floor_y: float
    zone: str


@dataclass
class PersonProfile:
    """Accumulated state for a single globally-tracked person."""

    global_id: int
    first_seen: float = 0.0
    last_seen: float = 0.0

    # Raw sub-scores (0-100 each)
    pose_score: float = 0.0
    scene_score: float = 0.0
    attribute_score: float = 0.0
    trajectory_score: float = 0.0
    temporal_score: float = 0.0
    social_score: float = 0.0

    # EMA-smoothed crime coefficient (0-300)
    crime_coefficient: float = 0.0

    # History for trajectory analysis
    trajectory: deque[TrajectoryPoint] = field(
        default_factory=lambda: deque(maxlen=600)  # ~5 min at 2Hz
    )
    zone_history: deque[tuple[float, str]] = field(
        default_factory=lambda: deque(maxlen=120)
    )

    # Score history for trend analysis
    score_history: deque[tuple[float, float]] = field(
        default_factory=lambda: deque(maxlen=60)
    )


class CrimeCoefficient:
    """Aggregates VAD signals into per-person crime coefficient.

    Designed to plug into CrossCameraTracker's GlobalTrack lifecycle:
    - update() called per-frame with raw scores from each VAD layer
    - get_coefficient() returns smoothed per-person score
    - evict() cleans up when a person departs
    """

    def __init__(
        self,
        ema_alpha: float = 0.1,
        restricted_zones: list[str] | None = None,
        normal_hours: tuple[int, int] = (7, 22),  # 7:00-22:00
        loiter_threshold_sec: float = 300.0,
        loiter_radius_m: float = 2.0,
    ):
        self._alpha = ema_alpha
        self._restricted_zones = set(restricted_zones or [])
        self._normal_hours = normal_hours
        self._loiter_threshold = loiter_threshold_sec
        self._loiter_radius = loiter_radius_m
        self._profiles: dict[int, PersonProfile] = {}

    def update(
        self,
        global_id: int,
        *,
        pose_score: float | None = None,
        scene_score: float | None = None,
        attribute_scores: dict[str, float] | None = None,
        floor_position: list[float] | None = None,
        zone: str = "",
        timestamp: float | None = None,
        nearby_person_count: int = 0,
    ):
        """Update crime coefficient for a person.

        All scores are optional — only provided sub-scores are updated.
        """
        now = timestamp or time.time()
        profile = self._get_or_create(global_id, now)
        profile.last_seen = now

        # --- Update raw sub-scores ---
        if pose_score is not None:
            profile.pose_score = self._clamp_score(pose_score)

        if scene_score is not None:
            profile.scene_score = self._clamp_score(scene_score)

        if attribute_scores is not None:
            combined = attribute_scores.get("combined", 0.0)
            profile.attribute_score = self._clamp_score(combined)

        # --- Trajectory analysis ---
        if floor_position and floor_position != [0.0, 0.0]:
            profile.trajectory.append(
                TrajectoryPoint(now, floor_position[0], floor_position[1], zone)
            )
            profile.trajectory_score = self._compute_trajectory_score(profile)

        # --- Zone tracking ---
        if zone:
            profile.zone_history.append((now, zone))

        # --- Temporal anomaly ---
        profile.temporal_score = self._compute_temporal_score(now)

        # --- Social anomaly ---
        profile.social_score = self._compute_social_score(
            profile, nearby_person_count
        )

        # --- Compute weighted crime coefficient ---
        raw = (
            W_POSE * profile.pose_score
            + W_SCENE * profile.scene_score
            + W_ATTRIBUTE * profile.attribute_score
            + W_TRAJECTORY * profile.trajectory_score
            + W_TEMPORAL * profile.temporal_score
            + W_SOCIAL * profile.social_score
        ) * 3.0  # Scale to 0-300 range

        # EMA smoothing
        profile.crime_coefficient = (
            self._alpha * raw + (1 - self._alpha) * profile.crime_coefficient
        )

        profile.score_history.append((now, profile.crime_coefficient))

    def get_coefficient(self, global_id: int) -> float:
        """Get smoothed crime coefficient for a person."""
        profile = self._profiles.get(global_id)
        return profile.crime_coefficient if profile else 0.0

    def get_profile(self, global_id: int) -> PersonProfile | None:
        return self._profiles.get(global_id)

    def get_all_coefficients(self) -> dict[int, float]:
        return {gid: p.crime_coefficient for gid, p in self._profiles.items()}

    def get_severity(self, global_id: int) -> str:
        coeff = self.get_coefficient(global_id)
        if coeff >= CRITICAL_THRESHOLD:
            return "critical"
        elif coeff >= WARNING_THRESHOLD:
            return "warning"
        elif coeff >= CLEAR_THRESHOLD:
            return "latent"
        return "clear"

    def get_breakdown(self, global_id: int) -> dict | None:
        """Detailed score breakdown for a person."""
        profile = self._profiles.get(global_id)
        if not profile:
            return None
        return {
            "global_id": global_id,
            "crime_coefficient": round(profile.crime_coefficient, 1),
            "severity": self.get_severity(global_id),
            "breakdown": {
                "pose": round(profile.pose_score, 1),
                "scene": round(profile.scene_score, 1),
                "attribute": round(profile.attribute_score, 1),
                "trajectory": round(profile.trajectory_score, 1),
                "temporal": round(profile.temporal_score, 1),
                "social": round(profile.social_score, 1),
            },
            "duration_sec": round(profile.last_seen - profile.first_seen, 1),
            "zones_visited": list(set(z for _, z in profile.zone_history)),
        }

    def evict(self, global_id: int):
        """Remove profile when person departs."""
        self._profiles.pop(global_id, None)

    # --- Private methods ---

    def _get_or_create(self, global_id: int, now: float) -> PersonProfile:
        if global_id not in self._profiles:
            self._profiles[global_id] = PersonProfile(
                global_id=global_id, first_seen=now, last_seen=now
            )
        return self._profiles[global_id]

    def _compute_trajectory_score(self, profile: PersonProfile) -> float:
        """Score based on loitering detection and restricted zone access."""
        score = 0.0
        traj = profile.trajectory
        if len(traj) < 10:
            return 0.0

        # --- Loitering detection ---
        # Check if person has stayed within a small radius for too long
        recent = [t for t in traj if profile.last_seen - t.timestamp < self._loiter_threshold]
        if len(recent) > 20:
            positions = np.array([[t.floor_x, t.floor_y] for t in recent])
            centroid = positions.mean(axis=0)
            distances = np.linalg.norm(positions - centroid, axis=1)
            if distances.max() < self._loiter_radius:
                duration = recent[-1].timestamp - recent[0].timestamp
                ratio = min(duration / self._loiter_threshold, 1.0)
                score += ratio * 60  # Up to 60 points for loitering

        # --- Restricted zone access ---
        if self._restricted_zones:
            recent_zones = set(t.zone for t in list(traj)[-30:])
            restricted_hits = recent_zones & self._restricted_zones
            if restricted_hits:
                score += 40  # 40 points for being in restricted zone

        return min(score, 100.0)

    def _compute_temporal_score(self, now: float) -> float:
        """Score based on presence outside normal hours."""
        import datetime

        dt = datetime.datetime.fromtimestamp(now)
        hour = dt.hour
        start, end = self._normal_hours

        if start <= hour < end:
            return 0.0

        # Distance from normal hours (max at midpoint of off-hours)
        if hour < start:
            dist = start - hour
        else:
            dist = hour - end
        # Max distance = 12 hours
        return min(dist / 6.0, 1.0) * 80  # Up to 80 points

    def _compute_social_score(
        self, profile: PersonProfile, nearby_count: int
    ) -> float:
        """Score based on unusual proximity patterns.

        Lone person in normally populated area or unusual crowding.
        """
        # Simple: being alone is slightly suspicious in an office
        # More sophisticated models would compare against zone baseline
        if nearby_count == 0:
            return 20.0  # Mild: alone
        return 0.0

    @staticmethod
    def _clamp_score(raw: float) -> float:
        """Convert raw anomaly score to 0-100 range using sigmoid-like scaling."""
        # Raw scores from detectors are typically in z-score space (0-10+)
        # Map: 0→0, 3→50, 5→80, 8→95, 10+→99
        if raw <= 0:
            return 0.0
        scaled = 100.0 * (1.0 - math.exp(-raw / 3.0))
        return min(scaled, 100.0)
