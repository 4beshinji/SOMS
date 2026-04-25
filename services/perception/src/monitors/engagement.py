"""
Engagement Monitor — face/posture/gesture cues from a single camera
(typically the dashboard's USB webcam) to drive Brain `speak` reactions.

Publishes two MQTT topics per cycle:

  office/{zone}/camera/{cam}/engagement
      Per-frame snapshot for WorldModel context (idempotent, low-frequency
      consumers welcome).

  office/{zone}/camera/{cam}/engagement_event
      Edge-triggered events (looked_at, waved, head_down, ...) one
      message per detected transition. Brain reacts to these to fire
      `speak`.
"""
import logging
import time

import numpy as np

from monitors.base import MonitorBase
from yolo_inference import YOLOInference
from pose_estimator import PoseEstimator
from state_publisher import StatePublisher
from engagement_analyzer import EngagementAnalyzer

logger = logging.getLogger(__name__)


class EngagementMonitor(MonitorBase):
    def __init__(
        self,
        camera_id: str,
        zone_name: str = "default",
        image_source=None,
        interval_sec: float = 1.0,
    ):
        super().__init__(
            name=f"EngagementMonitor_{zone_name}",
            camera_id=camera_id,
            interval_sec=interval_sec,
            resolution="VGA",
            quality=20,
            image_source=image_source,
        )
        self.zone_name = zone_name
        self.yolo = YOLOInference.get_instance()
        self.pose = PoseEstimator.get_instance()
        self.publisher = StatePublisher.get_instance()
        self.analyzer = EngagementAnalyzer()

    async def analyze(self, image: np.ndarray):
        # Tier 1: cheap person detection
        detections = self.yolo.infer(image, conf_threshold=0.5)
        persons_det = self.yolo.filter_by_class(detections, "person")
        if not persons_det:
            return {"persons_pose": [], "image_shape": image.shape}

        # Tier 2: pose
        persons_pose = self.pose.estimate(image, conf_threshold=0.4)
        return {"persons_pose": persons_pose, "image_shape": image.shape}

    async def process_results(self, analysis):
        persons_pose = analysis.get("persons_pose", [])
        image_shape = analysis.get("image_shape", (0, 0, 0))
        events, snapshots = self.analyzer.analyze(
            persons_pose, image_shape[:2], now=time.time()
        )

        # Compact snapshot payload for WorldModel
        snap_payload = {
            "zone": self.zone_name,
            "camera_id": self.camera_id,
            "person_count": len(snapshots),
            "persons": snapshots,
            "timestamp": time.time(),
        }
        snap_topic = f"office/{self.zone_name}/camera/{self.camera_id}/engagement"
        await self.publisher.publish(snap_topic, snap_payload)

        # One MQTT message per edge-triggered event so Brain can react
        # individually (it subscribes to `office/#` already).
        event_topic = f"office/{self.zone_name}/camera/{self.camera_id}/engagement_event"
        for ev in events:
            ev_payload = {
                "zone": self.zone_name,
                "camera_id": self.camera_id,
                **ev,
            }
            await self.publisher.publish(event_topic, ev_payload)
            logger.info(
                "[%s] event=%s track=%s orient=%s att=%s posture=%s",
                self.name,
                ev.get("event"),
                ev.get("track_key"),
                ev.get("face_orientation"),
                ev.get("attention"),
                ev.get("posture"),
            )
