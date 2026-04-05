"""
Activity Monitor — two-tier person detection + pose estimation.

Tier 1 (every cycle): lightweight YOLO person detection.
  → No person? Skip pose.
Tier 2 (only when persons found): YOLO-Pose skeleton extraction.
  → Feed keypoints into tiered ActivityAnalyzer.
  → Publish activity level + posture stasis to MQTT.
"""
import time
import logging
import numpy as np

from monitors.base import MonitorBase
from yolo_inference import YOLOInference
from pose_estimator import PoseEstimator
from activity_analyzer import ActivityAnalyzer
from state_publisher import StatePublisher
from fall_detector import FallDetector

logger = logging.getLogger(__name__)


class ActivityMonitor(MonitorBase):
    def __init__(
        self,
        camera_id: str,
        zone_name: str = "default",
        image_source=None,
        fall_detection_config: dict = None,
        vlm_analyzer=None,
    ):
        super().__init__(
            name=f"ActivityMonitor_{zone_name}",
            camera_id=camera_id,
            interval_sec=3.0,
            resolution="VGA",
            quality=15,
            image_source=image_source,
        )
        self.zone_name = zone_name
        self.yolo = YOLOInference.get_instance()
        self.pose = PoseEstimator.get_instance()
        self.publisher = StatePublisher.get_instance()
        self.analyzer = ActivityAnalyzer(frame_size=(800, 600))

        # Fall detection (optional, enabled via config)
        fd_cfg = fall_detection_config or {}
        if fd_cfg.get("enabled", False):
            self.fall_detector = FallDetector(
                torso_angle_threshold=fd_cfg.get("torso_angle_threshold", 60.0),
                fall_confidence_threshold=fd_cfg.get("fall_confidence_threshold", 0.5),
                confirmation_sec=fd_cfg.get("confirmation_sec", 5.0),
                recovery_sec=fd_cfg.get("recovery_sec", 10.0),
                alert_cooldown_sec=fd_cfg.get("alert_cooldown_sec", 120.0),
                furniture_iou_threshold=fd_cfg.get("furniture_iou_threshold", 0.15),
                transition_window_sec=fd_cfg.get("transition_window_sec", 1.0),
            )
            logger.info(f"[{self.name}] Fall detection enabled")
        else:
            self.fall_detector = None

        # VLM escalation (optional, injected externally)
        self._vlm_analyzer = vlm_analyzer
        self._prev_person_count = 0
        self._last_frame = None
        # Set of camera IDs that have a dedicated TrackingMonitor.
        # When set, spatial publish is skipped for these cameras to
        # avoid overwriting richer tracking data on the same MQTT topic.
        self._tracking_camera_ids: set[str] = set()

    async def analyze(self, image: np.ndarray):
        """Two-tier: detect → pose (only if persons found)."""
        self._last_frame = image
        # Tier 1: cheap person detection
        detections = self.yolo.infer(image, conf_threshold=0.5)
        persons_det = self.yolo.filter_by_class(detections, "person")

        if not persons_det:
            return {
                "person_count": 0,
                "persons_pose": [],
                "image_shape": image.shape,
                "all_detections": detections,
                "person_detections": [],
            }

        # Tier 2: pose estimation (only runs when we have persons)
        persons_pose = self.pose.estimate(image, conf_threshold=0.4)

        return {
            "person_count": len(persons_det),
            "persons_pose": persons_pose,
            "image_shape": image.shape,
            "all_detections": detections,
            "person_detections": persons_det,
        }

    async def process_results(self, analysis):
        """Feed poses into analyzer and publish activity + posture status."""
        person_count = analysis["person_count"]
        persons_pose = analysis["persons_pose"]

        if persons_pose:
            h, w = analysis["image_shape"][:2]
            self.analyzer._diag = float(np.hypot(w, h))
            self.analyzer.push(persons_pose)

        result = self.analyzer.analyze()

        payload = {
            "zone": self.zone_name,
            "person_count": person_count,
            "activity_level": result["activity_level"],
            "activity_class": result["activity_class"],
            "posture_duration_sec": result["posture_duration_sec"],
            "posture_status": result["posture_status"],
            "buffer_depth": result["buffer_depth"],
            "timestamp": time.time(),
        }

        topic = f"office/{self.zone_name}/activity"
        await self.publisher.publish(topic, payload)

        logger.info(
            f"[{self.name}] persons={person_count} "
            f"activity={result['activity_level']:.3f} ({result['activity_class']}) "
            f"posture={result['posture_status']} "
            f"({result['posture_duration_sec']:.0f}s) "
            f"buf={result['buffer_depth']}"
        )

        # Publish spatial detection data (bbox centers + classes, no raw images)
        # Skip if a TrackingMonitor covers this camera (it publishes richer data)
        person_detections = analysis.get("person_detections", [])
        all_detections = analysis.get("all_detections", [])
        if self.camera_id in self._tracking_camera_ids:
            pass  # TrackingMonitor handles spatial publish for this camera
        elif person_detections or all_detections:
            h, w = analysis["image_shape"][:2]
            persons_spatial = [
                {
                    "center_px": det["center"],
                    "bbox_px": det["bbox"],
                    "confidence": det["confidence"],
                }
                for det in person_detections
            ]
            objects_spatial = [
                {
                    "class_name": det["class"],
                    "center_px": det["center"],
                    "bbox_px": det["bbox"],
                    "confidence": det["confidence"],
                }
                for det in all_detections
                if det["class"] != "person"
            ]
            spatial_payload = {
                "zone": self.zone_name,
                "camera_id": self.camera_id,
                "timestamp": time.time(),
                "image_size": [w, h],
                "persons": persons_spatial,
                "objects": objects_spatial,
            }
            spatial_topic = f"office/{self.zone_name}/spatial/{self.camera_id}"
            await self.publisher.publish(spatial_topic, spatial_payload)

        # --- Fall detection ---
        fall_alerts = []
        if self.fall_detector and persons_pose:
            fall_alerts = self.fall_detector.update(
                persons_pose,
                analysis.get("all_detections", []),
                analysis["image_shape"],
            )
            for alert in fall_alerts:
                fall_payload = {
                    "zone": self.zone_name,
                    "confidence": alert.confidence,
                    "duration_sec": alert.duration_sec,
                    "bbox": alert.bbox,
                    "tracker_id": alert.tracker_id,
                    "timestamp": time.time(),
                }
                fall_topic = f"office/{self.zone_name}/safety/fall"
                await self.publisher.publish(fall_topic, fall_payload)
                logger.warning(
                    f"[{self.name}] FALL DETECTED: conf={alert.confidence:.2f} "
                    f"duration={alert.duration_sec:.1f}s"
                )

        # --- VLM escalation ---
        if self._vlm_analyzer and self._last_frame is not None:
            import asyncio as _asyncio

            # Occupancy change
            if person_count != self._prev_person_count:
                _asyncio.create_task(self._vlm_analyzer.request_analysis(
                    self._last_frame, "occupancy_change", self.zone_name,
                    {"person_count": person_count, "prev_count": self._prev_person_count},
                ))

            # Fall candidate
            if fall_alerts:
                _asyncio.create_task(self._vlm_analyzer.request_analysis(
                    self._last_frame, "fall_candidate", self.zone_name,
                    {"confidence": fall_alerts[0].confidence},
                ))

            self._prev_person_count = person_count
