"""VAD Monitor — integrates three-layer video anomaly detection with MTMC tracking.

Hooks into ActivityMonitor's pose output and CrossCameraTracker's global tracks
to compute per-person crime coefficients.

Does NOT duplicate YOLO/Pose inference — reuses existing detection results.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from tracking.cross_camera_tracker import CrossCameraTracker

logger = logging.getLogger(__name__)

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from vad.aed_mae import AEDMAEDetector
from vad.attribute_vad import AttributeVADDetector
from vad.ensemble import CrimeCoefficient
from vad.stg_nf import STGNFDetector


class VADMonitor:
    """Manages all three VAD detectors and crime coefficient computation.

    Not a MonitorBase subclass — instead, receives data from other monitors.
    This avoids duplicating YOLO/Pose inference.

    Integration points:
    - process_frame(): called by ActivityMonitor after pose estimation
    - update_tracking(): called by MTMCPublisher on each publish cycle
    - get_crime_coefficients(): read by MTMCPublisher for MQTT payload
    """

    def __init__(
        self,
        cross_camera_tracker: CrossCameraTracker | None = None,
        model_dir: str = "/app/model_store/vad",
        device: str = "cpu",
        restricted_zones: list[str] | None = None,
    ):
        self._tracker = cross_camera_tracker
        self._device = device

        # --- Layer 1: STG-NF (pose sequence anomaly) ---
        stg_path = os.path.join(model_dir, "stg_nf.pt")
        self._stg_nf = STGNFDetector(
            seq_len=24,
            model_path=stg_path if os.path.exists(stg_path) else None,
            device=device,
        )

        # --- Layer 2: AED-MAE (frame reconstruction anomaly) ---
        mae_path = os.path.join(model_dir, "aed_mae.pt")
        self._aed_mae = AEDMAEDetector(
            model_path=mae_path if os.path.exists(mae_path) else None,
            device=device,
        )

        # --- Layer 3: AI-VAD (attribute-based anomaly) ---
        attr_path = os.path.join(model_dir, "attribute_vad.pt")
        self._attr_vad = AttributeVADDetector(
            model_path=attr_path if os.path.exists(attr_path) else None,
            device=device,
        )

        # --- Ensemble: Crime Coefficient ---
        self._crime = CrimeCoefficient(
            restricted_zones=restricted_zones,
        )

        self._frame_count = 0
        self._last_scene_score: float | None = None

        logger.info(
            "VADMonitor initialized (device=%s, layers=3, restricted_zones=%s)",
            device,
            restricted_zones,
        )

    def process_frame(
        self,
        frame: np.ndarray,
        persons_pose: list[dict],
        person_detections: list[dict],
        zone: str,
        timestamp: float | None = None,
    ):
        """Process one frame from ActivityMonitor.

        Called after YOLO detection + pose estimation. Does NOT re-run
        detection — only runs VAD-specific models.

        Args:
            frame: (H, W, 3) BGR image
            persons_pose: list of {keypoints, keypoint_conf, bbox, confidence}
            person_detections: list of {class, bbox, center, confidence}
            zone: zone identifier
            timestamp: frame timestamp
        """
        now = timestamp or time.time()
        self._frame_count += 1

        # --- Layer 2: AED-MAE (every 3rd frame to save compute) ---
        if self._frame_count % 3 == 0:
            self._last_scene_score = self._aed_mae.score_frame(frame)

        # --- Per-person processing ---
        for i, person in enumerate(persons_pose):
            kp = person.get("keypoints")
            conf = person.get("keypoint_conf")
            bbox = person.get("bbox", [0, 0, 0, 0])

            if kp is None or conf is None:
                continue

            # Resolve global ID from tracker
            global_id = self._resolve_global_id(zone, bbox, i)
            if global_id is None:
                continue

            # Layer 1: STG-NF pose anomaly
            pose_score = self._stg_nf.update(global_id, kp, conf)

            # Layer 3: AI-VAD attribute anomaly
            attrs = self._attr_vad.extract_attributes(
                person_id=global_id,
                bbox=bbox,
                keypoints=kp,
                confidences=conf,
                frame=frame,
                timestamp=now,
            )
            attr_scores = self._attr_vad.score(attrs) if attrs else None

            # Get nearby person count for social scoring
            nearby = len(persons_pose) - 1

            # Get floor position from tracker
            floor_pos = self._get_floor_position(global_id)

            # Update crime coefficient
            self._crime.update(
                global_id,
                pose_score=pose_score,
                scene_score=self._last_scene_score,
                attribute_scores=attr_scores,
                floor_position=floor_pos,
                zone=zone,
                timestamp=now,
                nearby_person_count=nearby,
            )

    def get_crime_coefficients(self) -> dict[int, float]:
        """Return all active crime coefficients."""
        return self._crime.get_all_coefficients()

    def get_breakdown(self, global_id: int) -> dict | None:
        """Get detailed score breakdown for a person."""
        return self._crime.get_breakdown(global_id)

    def get_all_breakdowns(self) -> list[dict]:
        """Get breakdowns for all tracked persons."""
        return [
            b for gid in self._crime.get_all_coefficients()
            if (b := self._crime.get_breakdown(gid)) is not None
        ]

    def evict_person(self, global_id: int):
        """Clean up when a person departs."""
        self._stg_nf.evict(global_id)
        self._attr_vad.evict(global_id)
        self._crime.evict(global_id)

    def _resolve_global_id(
        self, zone: str, bbox: list[float], fallback_idx: int
    ) -> int | None:
        """Map a detection bbox to a global person ID via the cross-camera tracker."""
        if self._tracker is None:
            # No tracker — use detection index as pseudo-ID
            return fallback_idx

        # Find the global track whose latest detection bbox overlaps most
        tracks = self._tracker.get_global_tracks()
        if not tracks:
            return fallback_idx

        best_iou = 0.0
        best_gid = None

        for track in tracks:
            if track.zone_id != zone:
                continue
            for tracklet in track.tracklets.values():
                if tracklet.detections:
                    det = tracklet.detections[-1]
                    iou = self._bbox_iou(bbox, det.bbox_px)
                    if iou > best_iou:
                        best_iou = iou
                        best_gid = track.global_id

        return best_gid if best_iou > 0.3 else fallback_idx

    def _get_floor_position(self, global_id: int) -> list[float] | None:
        """Get floor position from tracker."""
        if self._tracker is None:
            return None
        tracks = self._tracker.get_global_tracks()
        for track in tracks:
            if track.global_id == global_id:
                return track.floor_position
        return None

    @staticmethod
    def _bbox_iou(a: list[float], b: list[float]) -> float:
        """Compute IoU between two [x1, y1, x2, y2] bboxes."""
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])

        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        if intersection == 0:
            return 0.0

        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        union = area_a + area_b - intersection

        return intersection / union if union > 0 else 0.0
