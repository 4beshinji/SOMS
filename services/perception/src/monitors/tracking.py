"""
Tracking Monitor — per-camera BoT-SORT SCT + ReID extraction.

Runs YOLO model.track() with persist=True for single-camera tracking,
extracts ReID embeddings, projects foot points to floor coordinates,
and feeds results into the shared CrossCameraTracker.

Each camera gets its own YOLO instance to maintain separate tracker state.
"""
import time
import logging
from pathlib import Path

import numpy as np
from ultralytics import YOLO

from monitors.base import MonitorBase
from state_publisher import StatePublisher
from tracking.tracklet import TrackedPerson
from tracking.homography import foot_from_bbox, pixel_to_floor
from tracking.reid_embedder import ReIDEmbedder

logger = logging.getLogger(__name__)

# Default tracker config relative to perception config dir
_DEFAULT_TRACKER_CFG = str(
    Path(__file__).parent.parent.parent / "config" / "tracker" / "botsort.yaml"
)


class TrackingMonitor(MonitorBase):
    """Per-camera person tracker using BoT-SORT + ReID."""

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
            interval_sec=0.2,  # 5 FPS
            resolution="VGA",
            quality=15,
            image_source=image_source,
        )
        self.zone_name = zone_name
        self._cross_tracker = cross_camera_tracker
        self._publisher = StatePublisher.get_instance()
        self._reid = ReIDEmbedder.get_instance()
        self._tracker_config = tracker_config or _DEFAULT_TRACKER_CFG

        # Each camera needs its own YOLO instance for independent tracker state
        logger.info("Loading YOLO tracker for %s: %s", camera_id, model_path)
        self._yolo = YOLO(model_path)

    async def analyze(self, image: np.ndarray):
        """
        Run BoT-SORT tracking + ReID extraction.

        Returns list of TrackedPerson dataclass instances.
        """
        # BoT-SORT: persist=True keeps tracker state across frames
        results = self._yolo.track(
            image,
            persist=True,
            tracker=self._tracker_config,
            classes=[0],  # person class only
            verbose=False,
            conf=0.5,
        )

        if not results or results[0].boxes is None:
            return []

        boxes = results[0].boxes
        if boxes.id is None:
            # No tracks assigned yet
            return []

        track_ids = boxes.id.cpu().numpy().astype(int)
        bboxes = boxes.xyxy.cpu().numpy()  # (N, 4)
        confs = boxes.conf.cpu().numpy()

        # Batch ReID extraction
        bbox_list = bboxes.tolist()
        embeddings = self._reid.extract(image, bbox_list)

        timestamp = time.time()
        persons = []

        for i, (track_id, bbox, conf) in enumerate(zip(track_ids, bboxes, confs)):
            bbox_f = bbox.tolist()
            foot_px = foot_from_bbox(bbox_f)
            foot_floor = pixel_to_floor(self.camera_id, foot_px) or [0.0, 0.0]

            embedding = embeddings[i] if i < len(embeddings) else np.zeros(512)

            persons.append(TrackedPerson(
                track_id=int(track_id),
                camera_id=self.camera_id,
                bbox_px=bbox_f,
                foot_px=foot_px,
                foot_floor=foot_floor,
                confidence=float(conf),
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
