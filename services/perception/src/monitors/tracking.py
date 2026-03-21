"""
Tracking Monitor — per-camera BoT-SORT SCT + ReID extraction.

Uses the shared YOLOInference singleton for detection (single GPU model),
and a lightweight per-camera BOTSORT tracker for temporal association.
Extracts ReID embeddings, projects foot points to floor coordinates,
and feeds results into the shared CrossCameraTracker.
"""
import time
import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from ultralytics.trackers import BOTSORT

from monitors.base import MonitorBase
from state_publisher import StatePublisher
from yolo_inference import YOLOInference
from tracking.tracklet import TrackedPerson
from tracking.homography import foot_from_bbox, pixel_to_floor
from tracking.reid_embedder import ReIDEmbedder

logger = logging.getLogger(__name__)

# Default BOTSORT parameters (matches ultralytics/cfg/trackers/botsort.yaml)
_DEFAULT_BOTSORT_ARGS = SimpleNamespace(
    tracker_type="botsort",
    track_high_thresh=0.25,
    track_low_thresh=0.1,
    new_track_thresh=0.25,
    track_buffer=30,
    match_thresh=0.8,
    fuse_score=True,
    gmc_method="sparseOptFlow",
    proximity_thresh=0.5,
    appearance_thresh=0.8,
    with_reid=False,
    model="auto",
)


class TrackingMonitor(MonitorBase):
    """Per-camera person tracker using shared YOLO + per-camera BOTSORT."""

    def __init__(
        self,
        camera_id: str,
        zone_name: str,
        cross_camera_tracker,
        model_path: str = "yolo11s.pt",
        tracker_config: str | None = None,
        image_source=None,
    ):
        super().__init__(
            name=f"Tracking_{camera_id}",
            camera_id=camera_id,
            interval_sec=1.0,
            resolution="VGA",
            quality=15,
            image_source=image_source,
        )
        self.zone_name = zone_name
        self._cross_tracker = cross_camera_tracker
        self._publisher = StatePublisher.get_instance()
        self._reid = ReIDEmbedder.get_instance()

        # Shared YOLO singleton — no extra GPU memory per camera
        self._yolo = YOLOInference.get_instance(model_path)

        # Lightweight per-camera tracker (CPU only, ~few MB each)
        self._botsort = BOTSORT(_DEFAULT_BOTSORT_ARGS, frame_rate=1)
        logger.info("TrackingMonitor %s: shared YOLO + per-camera BOTSORT", camera_id)

    async def analyze(self, image: np.ndarray):
        """
        Run shared YOLO detect + per-camera BOTSORT tracking + ReID.

        Returns list of TrackedPerson dataclass instances.
        """
        # Shared YOLO inference (person class only)
        results = self._yolo.model(image, verbose=False, conf=0.5, classes=[0])

        # Move boxes to CPU for BOTSORT (which uses numpy internally)
        boxes = results[0].boxes.cpu() if results and results[0].boxes is not None else None

        if boxes is None or len(boxes) == 0:
            if boxes is not None:
                self._botsort.update(boxes, image)
            return []

        # Per-camera BOTSORT tracking (CPU, lightweight)
        tracked = self._botsort.update(boxes, image)
        # tracked: ndarray shape (N, 7) — [x1, y1, x2, y2, track_id, conf, cls]

        if len(tracked) == 0:
            return []

        # ReID extraction
        bboxes = tracked[:, :4].tolist()
        embeddings = self._reid.extract(image, bboxes)

        timestamp = time.time()
        persons = []

        for i, row in enumerate(tracked):
            x1, y1, x2, y2 = row[:4]
            track_id = int(row[4])
            conf = float(row[5])

            bbox_f = [float(x1), float(y1), float(x2), float(y2)]
            foot_px = foot_from_bbox(bbox_f)
            foot_floor = pixel_to_floor(self.camera_id, foot_px) or [0.0, 0.0]

            embedding = embeddings[i] if i < len(embeddings) else np.zeros(512)

            persons.append(TrackedPerson(
                track_id=track_id,
                camera_id=self.camera_id,
                bbox_px=bbox_f,
                foot_px=foot_px,
                foot_floor=foot_floor,
                confidence=conf,
                reid_embedding=embedding,
                timestamp=timestamp,
            ))

        return persons

    async def process_results(self, detections: list[TrackedPerson]):
        """Feed detections into cross-camera tracker and publish spatial data."""
        timestamp = time.time()

        # Update cross-camera tracker
        self._cross_tracker.update_camera(self.camera_id, detections)

        # Publish backward-compatible spatial data (with track_id added)
        persons_spatial = []
        for det in detections:
            x1, y1, x2, y2 = det.bbox_px
            persons_spatial.append({
                "center_px": [(x1 + x2) / 2.0, (y1 + y2) / 2.0],
                "bbox_px": det.bbox_px,
                "confidence": det.confidence,
                "track_id": det.track_id,
                "floor_position_m": det.foot_floor,
            })

        spatial_payload = {
            "zone": self.zone_name,
            "camera_id": self.camera_id,
            "timestamp": timestamp,
            "image_size": [640, 480],  # VGA
            "persons": persons_spatial,
            "objects": [],
        }

        topic = f"office/{self.zone_name}/spatial/{self.camera_id}"
        await self._publisher.publish(topic, spatial_payload)

        if detections:
            logger.debug(
                "[%s] %d persons tracked (IDs: %s)",
                self.name,
                len(detections),
                [d.track_id for d in detections],
            )
