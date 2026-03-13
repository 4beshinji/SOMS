"""
Cross-Camera Tracker — associates tracklets across cameras using
ReID embeddings, spatial proximity, and temporal constraints.

Uses Hungarian algorithm (scipy.optimize.linear_sum_assignment) for
optimal global ID assignment.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Optional

import numpy as np
from scipy.optimize import linear_sum_assignment

from tracking.tracklet import TrackedPerson, Tracklet, GlobalTrack
from tracking.homography import floor_distance, point_in_zone
from tracking.reid_embedder import ReIDEmbedder

logger = logging.getLogger(__name__)

# Maximum stored embeddings for re-identification of disappeared persons
_MAX_EMBEDDING_HISTORY = 200


class CrossCameraTracker:
    """
    Maintains global person identities across multiple cameras.

    Workflow:
    1. TrackingMonitor calls update_camera() with per-camera detections.
    2. Detections are mapped to existing tracklets (by camera + local ID).
    3. Unassigned tracklets are matched to global tracks via cost matrix.
    4. New global IDs are created for truly new persons.
    """

    def __init__(
        self,
        zone_polygons: dict[str, list[list[float]]],
        reid_weight: float = 0.5,
        spatial_weight: float = 0.3,
        temporal_weight: float = 0.2,
        match_threshold: float = 0.5,
        spatial_gate_m: float = 5.0,
        temporal_gate_s: float = 30.0,
        tracklet_timeout_s: float = 60.0,
        global_track_timeout_s: float = 300.0,
        wifi_spatial_weight: float = 0.7,
        wifi_temporal_weight: float = 0.3,
        wifi_spatial_gate_m: float = 8.0,
    ):
        self._zone_polygons = zone_polygons
        self._reid_weight = reid_weight
        self._spatial_weight = spatial_weight
        self._temporal_weight = temporal_weight
        self._match_threshold = match_threshold
        self._spatial_gate = spatial_gate_m
        self._temporal_gate = temporal_gate_s
        self._tracklet_timeout = tracklet_timeout_s
        self._global_timeout = global_track_timeout_s
        self._wifi_spatial_weight = wifi_spatial_weight
        self._wifi_temporal_weight = wifi_temporal_weight
        self._wifi_spatial_gate = wifi_spatial_gate_m

        # Active tracklets: (camera_id, local_track_id) -> Tracklet
        self._tracklets: dict[tuple[str, int], Tracklet] = {}

        # Global tracks: global_id -> GlobalTrack
        self._global_tracks: dict[int, GlobalTrack] = {}
        self._next_global_id = 1

        # Embedding history for re-identification after disappearance
        self._embedding_history: deque[tuple[int, np.ndarray]] = deque(
            maxlen=_MAX_EMBEDDING_HISTORY
        )

    def update_camera(
        self, camera_id: str, detections: list[TrackedPerson]
    ):
        """
        Process new detections from a single camera.

        Args:
            camera_id: Source camera identifier.
            detections: List of TrackedPerson from TrackingMonitor.
        """
        now = time.time()

        # Update or create tracklets for each detection
        active_keys = set()
        for det in detections:
            key = (camera_id, det.track_id)
            active_keys.add(key)

            if key not in self._tracklets:
                self._tracklets[key] = Tracklet(
                    camera_id=camera_id,
                    local_track_id=det.track_id,
                )

            tracklet = self._tracklets[key]
            tracklet.detections.append(det)
            tracklet.last_seen = det.timestamp
            tracklet.update_embedding()

        # Try to assign unassigned tracklets to global tracks
        self._associate_tracklets(now)

        # Expire old tracklets and global tracks
        self._cleanup(now)

    def _associate_tracklets(self, now: float):
        """Match unassigned tracklets to global tracks (or create new ones)."""
        unassigned = [
            t for t in self._tracklets.values()
            if t.global_id is None and t.avg_embedding is not None
        ]

        if not unassigned:
            return

        active_globals = list(self._global_tracks.values())

        if not active_globals:
            # No existing globals — create new ones for all unassigned
            for tracklet in unassigned:
                self._create_global_track(tracklet, now)
            return

        # Build cost matrix: rows=unassigned tracklets, cols=global tracks
        n_tracklets = len(unassigned)
        n_globals = len(active_globals)
        cost_matrix = np.full((n_tracklets, n_globals), 1e6, dtype=np.float64)

        for i, tracklet in enumerate(unassigned):
            for j, gtrack in enumerate(active_globals):
                # Skip if this tracklet's camera already has an active tracklet
                # in this global track (avoid double-counting from same camera)
                if tracklet.camera_id in gtrack.tracklets:
                    existing = gtrack.tracklets[tracklet.camera_id]
                    if existing.local_track_id != tracklet.local_track_id:
                        continue

                cost = self._compute_cost(tracklet, gtrack, now)
                if cost is not None:
                    cost_matrix[i, j] = cost

        # Hungarian algorithm
        row_idx, col_idx = linear_sum_assignment(cost_matrix)

        matched_tracklets = set()
        for i, j in zip(row_idx, col_idx):
            if cost_matrix[i, j] < (1.0 - self._match_threshold):
                tracklet = unassigned[i]
                gtrack = active_globals[j]
                self._assign_to_global(tracklet, gtrack)
                matched_tracklets.add(id(tracklet))

        # Create new global tracks for unmatched tracklets
        for tracklet in unassigned:
            if id(tracklet) not in matched_tracklets and tracklet.global_id is None:
                # Try re-identification from history
                reidentified = self._try_reidentify(tracklet)
                if not reidentified:
                    self._create_global_track(tracklet, now)

    def _is_wifi_tracklet(self, tracklet: Tracklet) -> bool:
        """Check if a tracklet originates from a WiFi source."""
        if not tracklet.detections:
            return False
        return tracklet.detections[-1].source_type == "wifi"

    def _compute_cost(
        self, tracklet: Tracklet, gtrack: GlobalTrack, now: float
    ) -> Optional[float]:
        """
        Compute association cost between a tracklet and global track.
        Lower is better. Returns None if gated out.

        WiFi tracklets use wider spatial gate and skip ReID (zero embeddings).
        """
        is_wifi = self._is_wifi_tracklet(tracklet)
        spatial_gate = self._wifi_spatial_gate if is_wifi else self._spatial_gate

        # Spatial gate
        t_pos = tracklet.latest_floor_position
        g_pos = gtrack.floor_position
        if t_pos and g_pos and t_pos != [0.0, 0.0] and g_pos != [0.0, 0.0]:
            dist = floor_distance(t_pos, g_pos)
            if dist > spatial_gate:
                return None
            spatial_score = 1.0 - min(dist / spatial_gate, 1.0)
        else:
            spatial_score = 0.5  # Unknown position — neutral

        # Temporal gate
        time_diff = abs(tracklet.last_seen - gtrack.last_seen)
        if time_diff > self._temporal_gate:
            return None
        temporal_score = 1.0 - min(time_diff / self._temporal_gate, 1.0)

        if is_wifi:
            # WiFi: no ReID (zero embeddings), spatial+temporal only
            score = (
                self._wifi_spatial_weight * spatial_score
                + self._wifi_temporal_weight * temporal_score
            )
        else:
            # Camera: full ReID + spatial + temporal
            if tracklet.avg_embedding is not None and gtrack.avg_embedding is not None:
                reid_score = float(np.dot(tracklet.avg_embedding, gtrack.avg_embedding))
                reid_score = max(0.0, reid_score)  # Clamp negative
            else:
                reid_score = 0.0

            score = (
                self._reid_weight * reid_score
                + self._spatial_weight * spatial_score
                + self._temporal_weight * temporal_score
            )

        # Return cost (lower = better for linear_sum_assignment)
        return 1.0 - score

    def _assign_to_global(self, tracklet: Tracklet, gtrack: GlobalTrack):
        """Link a tracklet to an existing global track."""
        tracklet.global_id = gtrack.global_id
        gtrack.tracklets[tracklet.camera_id] = tracklet
        gtrack.update_position()
        gtrack.update_embedding()
        gtrack.zone_id = self._resolve_zone(gtrack.floor_position)

    def _create_global_track(self, tracklet: Tracklet, now: float):
        """Create a new global track from an unassigned tracklet."""
        gid = self._next_global_id
        self._next_global_id += 1

        floor_pos = tracklet.latest_floor_position or [0.0, 0.0]
        zone = self._resolve_zone(floor_pos)

        gtrack = GlobalTrack(
            global_id=gid,
            tracklets={tracklet.camera_id: tracklet},
            last_seen=tracklet.last_seen,
            floor_position=floor_pos,
            zone_id=zone,
            first_seen=now,
            avg_embedding=tracklet.avg_embedding,
        )

        tracklet.global_id = gid
        self._global_tracks[gid] = gtrack

        logger.info(
            "New global track: id=%d camera=%s zone=%s",
            gid, tracklet.camera_id, zone,
        )

    def _try_reidentify(self, tracklet: Tracklet) -> bool:
        """Try to match tracklet against recently disappeared embeddings."""
        if tracklet.avg_embedding is None or not self._embedding_history:
            return False

        best_sim = 0.0
        best_gid = None

        for gid, emb in self._embedding_history:
            sim = float(np.dot(tracklet.avg_embedding, emb))
            if sim > best_sim:
                best_sim = sim
                best_gid = gid

        # High threshold for re-identification
        if best_sim > 0.7 and best_gid is not None:
            # Re-create global track with old ID
            if best_gid not in self._global_tracks:
                floor_pos = tracklet.latest_floor_position or [0.0, 0.0]
                gtrack = GlobalTrack(
                    global_id=best_gid,
                    tracklets={tracklet.camera_id: tracklet},
                    last_seen=tracklet.last_seen,
                    floor_position=floor_pos,
                    zone_id=self._resolve_zone(floor_pos),
                    first_seen=time.time(),
                    avg_embedding=tracklet.avg_embedding,
                )
                tracklet.global_id = best_gid
                self._global_tracks[best_gid] = gtrack
                logger.info(
                    "Re-identified person: global_id=%d sim=%.3f",
                    best_gid, best_sim,
                )
                return True

        return False

    def _resolve_zone(self, floor_xy: list[float]) -> str:
        """Determine which zone a floor point belongs to."""
        if floor_xy == [0.0, 0.0]:
            return ""
        for zone_id, polygon in self._zone_polygons.items():
            if point_in_zone(floor_xy, polygon):
                return zone_id
        return ""

    def _cleanup(self, now: float):
        """Expire old tracklets and global tracks."""
        # Expire tracklets
        expired_keys = [
            key for key, t in self._tracklets.items()
            if now - t.last_seen > self._tracklet_timeout
        ]
        for key in expired_keys:
            del self._tracklets[key]

        # Expire global tracks
        expired_globals = [
            gid for gid, g in self._global_tracks.items()
            if now - g.last_seen > self._global_timeout
        ]
        for gid in expired_globals:
            gtrack = self._global_tracks.pop(gid)
            # Save embedding for future re-identification
            if gtrack.avg_embedding is not None:
                self._embedding_history.append((gid, gtrack.avg_embedding))
            logger.info(
                "Global track expired: id=%d duration=%.0fs",
                gid, gtrack.duration_sec,
            )

    def get_global_tracks(self) -> list[GlobalTrack]:
        """Return all active global tracks."""
        return list(self._global_tracks.values())

    def get_person_count_by_zone(self) -> dict[str, int]:
        """Return person count per zone."""
        counts: dict[str, int] = {}
        for gtrack in self._global_tracks.values():
            zone = gtrack.zone_id
            if zone:
                counts[zone] = counts.get(zone, 0) + 1
        return counts
