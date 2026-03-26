"""
Data classes for person tracking across cameras.

TrackedPerson: Single detection with position and ReID embedding.
Tracklet: Per-camera track history (local BoT-SORT ID).
GlobalTrack: Cross-camera unified identity.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class TrackedPerson:
    """Single detected person in one frame from one camera."""
    track_id: int               # BoT-SORT local ID
    camera_id: str
    bbox_px: list[float]        # [x1, y1, x2, y2]
    foot_px: list[float]        # bbox bottom-center [x, y]
    foot_floor: list[float]     # floor coordinates [x_m, y_m]
    confidence: float
    reid_embedding: np.ndarray  # 512-dim L2-normalized
    timestamp: float
    source_type: str = "camera"  # "camera" | "wifi"


@dataclass
class Tracklet:
    """Per-camera track: local BoT-SORT ID + detection history."""
    camera_id: str
    local_track_id: int
    global_id: Optional[int] = None
    detections: deque[TrackedPerson] = field(
        default_factory=lambda: deque(maxlen=30)
    )
    last_seen: float = 0.0
    avg_embedding: Optional[np.ndarray] = None
    embedding_alpha: float = 0.15

    def update_embedding(self):
        """Exponential moving average of ReID embeddings."""
        if not self.detections:
            return
        latest = self.detections[-1].reid_embedding
        if self.avg_embedding is None:
            self.avg_embedding = latest.copy()
        else:
            alpha = self.embedding_alpha
            self.avg_embedding = alpha * latest + (1 - alpha) * self.avg_embedding
            # Re-normalize to unit vector
            norm = np.linalg.norm(self.avg_embedding)
            if norm > 0:
                self.avg_embedding /= norm

    @property
    def latest_floor_position(self) -> Optional[list[float]]:
        if self.detections:
            return self.detections[-1].foot_floor
        return None


@dataclass
class GlobalTrack:
    """Cross-camera unified identity."""
    global_id: int
    tracklets: dict[str, Tracklet] = field(default_factory=dict)  # camera_id -> Tracklet
    last_seen: float = 0.0
    floor_position: list[float] = field(default_factory=lambda: [0.0, 0.0])
    zone_id: str = ""
    first_seen: float = 0.0
    avg_embedding: Optional[np.ndarray] = None

    def update_position(self):
        """Update floor position from most recent tracklet detection.

        Skips [0.0, 0.0] positions (uncalibrated/failed projection) and
        prefers valid positions from any tracklet over the default origin.
        """
        best_ts = 0.0
        for tracklet in self.tracklets.values():
            pos = tracklet.latest_floor_position
            if pos and pos != [0.0, 0.0] and tracklet.last_seen > best_ts:
                best_ts = tracklet.last_seen
                self.floor_position = pos
        if best_ts > 0:
            self.last_seen = best_ts

    def update_embedding(self):
        """Average embeddings from all active tracklets."""
        embeddings = [
            t.avg_embedding for t in self.tracklets.values()
            if t.avg_embedding is not None
        ]
        if not embeddings:
            return
        stacked = np.stack(embeddings)
        self.avg_embedding = stacked.mean(axis=0)
        norm = np.linalg.norm(self.avg_embedding)
        if norm > 0:
            self.avg_embedding /= norm

    @property
    def duration_sec(self) -> float:
        if self.first_seen > 0 and self.last_seen > 0:
            return self.last_seen - self.first_seen
        return 0.0

    @property
    def camera_ids(self) -> list[str]:
        return list(self.tracklets.keys())

    @property
    def source_ids(self) -> list[str]:
        """Alias for camera_ids — includes WiFi source IDs if present."""
        return list(self.tracklets.keys())
