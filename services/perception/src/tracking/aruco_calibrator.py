"""
ArUco marker-based camera calibration for floor-plane homography.

Detects ArUco markers in camera frames, matches them to known world
coordinates from config/spatial.yaml, and computes per-camera
homography matrices using cv2.findHomography().

Singleton pattern matches existing YOLOInference / PoseEstimator.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ArucoCalibrator:
    _instance: Optional[ArucoCalibrator] = None

    @classmethod
    def get_instance(
        cls,
        aruco_markers: dict | None = None,
        aruco_dict_name: str = "DICT_4X4_50",
        cache_path: str | None = None,
    ) -> ArucoCalibrator:
        if cls._instance is None:
            cls._instance = cls(aruco_markers or {}, aruco_dict_name, cache_path)
        return cls._instance

    def __init__(
        self,
        aruco_markers: dict,
        aruco_dict_name: str = "DICT_4X4_50",
        cache_path: str | None = None,
    ):
        # aruco_markers: {marker_id: {"corners": [[x,y],[x,y],[x,y],[x,y]]}}
        # corners are floor-plane coordinates (meters)
        self._world_markers = aruco_markers
        self._cache_path = Path(cache_path) if cache_path else None

        # Per-camera homography: camera_id -> 3x3 np.ndarray
        self._homographies: dict[str, np.ndarray] = {}

        # ArUco detector setup
        dict_id = getattr(cv2.aruco, aruco_dict_name, cv2.aruco.DICT_4X4_50)
        self._aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
        self._aruco_params = cv2.aruco.DetectorParameters()
        self._detector = cv2.aruco.ArucoDetector(self._aruco_dict, self._aruco_params)

        # Try to load cached homographies
        self._load_cache()

        logger.info(
            "ArucoCalibrator initialized: %d world markers, dict=%s",
            len(self._world_markers),
            aruco_dict_name,
        )

    def _load_cache(self):
        """Load cached homography matrices from disk."""
        if not self._cache_path or not self._cache_path.exists():
            return
        try:
            data = json.loads(self._cache_path.read_text())
            for cam_id, h_list in data.items():
                self._homographies[cam_id] = np.array(h_list, dtype=np.float64)
            logger.info("Loaded calibration cache: %d cameras", len(self._homographies))
        except Exception as e:
            logger.warning("Failed to load calibration cache: %s", e)

    def _save_cache(self):
        """Persist homography matrices to disk."""
        if not self._cache_path:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                cam_id: h.tolist()
                for cam_id, h in self._homographies.items()
            }
            self._cache_path.write_text(json.dumps(data, indent=2))
            logger.info("Saved calibration cache: %d cameras", len(data))
        except Exception as e:
            logger.warning("Failed to save calibration cache: %s", e)

    def calibrate_camera(
        self,
        camera_id: str,
        image: np.ndarray,
        min_markers: int = 4,
    ) -> dict:
        """
        Detect ArUco markers in an image and compute homography.

        Args:
            camera_id: Unique camera identifier.
            image: BGR image from the camera.
            min_markers: Minimum markers required for valid calibration.

        Returns:
            dict with status, markers_detected, error (if any).
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)

        if ids is None or len(ids) < min_markers:
            detected = 0 if ids is None else len(ids)
            msg = (
                f"Insufficient markers for {camera_id}: "
                f"found {detected}, need {min_markers}"
            )
            logger.warning(msg)
            return {
                "camera_id": camera_id,
                "status": "failed",
                "markers_detected": detected,
                "error": msg,
            }

        # Build pixel ↔ world point correspondences
        # Each marker has 4 corners, giving 4 point pairs per marker
        pixel_points = []
        world_points = []

        for i, marker_id in enumerate(ids.flatten()):
            marker_id_str = str(int(marker_id))
            if marker_id_str not in self._world_markers:
                continue

            world_corners = self._world_markers[marker_id_str]["corners"]
            pixel_corners = corners[i][0]  # shape: (4, 2)

            for j in range(4):
                pixel_points.append(pixel_corners[j])
                world_points.append(world_corners[j])

        if len(pixel_points) < min_markers * 4:
            msg = (
                f"Not enough known markers for {camera_id}: "
                f"{len(pixel_points) // 4} matched of {min_markers} required"
            )
            logger.warning(msg)
            return {
                "camera_id": camera_id,
                "status": "failed",
                "markers_detected": len(ids),
                "error": msg,
            }

        pixel_pts = np.array(pixel_points, dtype=np.float64)
        world_pts = np.array(world_points, dtype=np.float64)

        H, mask = cv2.findHomography(pixel_pts, world_pts, cv2.RANSAC, 5.0)
        if H is None:
            msg = f"Homography computation failed for {camera_id}"
            logger.error(msg)
            return {
                "camera_id": camera_id,
                "status": "failed",
                "markers_detected": len(ids),
                "error": msg,
            }

        inliers = int(mask.sum()) if mask is not None else len(pixel_points)
        self._homographies[camera_id] = H
        self._save_cache()

        logger.info(
            "Calibrated %s: %d markers, %d/%d inlier points",
            camera_id, len(ids), inliers, len(pixel_points),
        )
        return {
            "camera_id": camera_id,
            "status": "ok",
            "markers_detected": len(ids),
            "inlier_points": inliers,
            "total_points": len(pixel_points),
        }

    async def calibrate_all(
        self,
        cameras: dict,
        image_sources: dict,
        min_markers: int = 4,
    ) -> list[dict]:
        """
        Calibrate all cameras. Captures one frame per camera.

        Args:
            cameras: {camera_id: camera_config_dict}
            image_sources: {camera_id: ImageSource instance}
            min_markers: Minimum markers per camera.

        Returns:
            List of calibration result dicts.
        """
        results = []
        for camera_id, source in image_sources.items():
            image = await source.capture()
            if image is None:
                results.append({
                    "camera_id": camera_id,
                    "status": "failed",
                    "markers_detected": 0,
                    "error": "Could not capture image",
                })
                continue
            result = self.calibrate_camera(camera_id, image, min_markers)
            results.append(result)
        return results

    def has_calibration(self, camera_id: str) -> bool:
        """Check if a camera has a valid homography."""
        return camera_id in self._homographies

    def project_to_floor(
        self, camera_id: str, pixel_xy: list[float]
    ) -> Optional[list[float]]:
        """
        Transform pixel coordinates to floor-plane meters.

        Args:
            camera_id: Camera identifier.
            pixel_xy: [x, y] in pixel space.

        Returns:
            [x_m, y_m] in floor coordinates, or None if not calibrated.
        """
        H = self._homographies.get(camera_id)
        if H is None:
            return None

        pt = np.array([[[pixel_xy[0], pixel_xy[1]]]], dtype=np.float64)
        transformed = cv2.perspectiveTransform(pt, H)
        return [float(transformed[0, 0, 0]), float(transformed[0, 0, 1])]

    def get_calibrated_cameras(self) -> list[str]:
        """List of camera IDs with valid homographies."""
        return list(self._homographies.keys())
