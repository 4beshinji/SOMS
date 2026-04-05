"""
Camera-geometry-based floor projection — ArUco-free fallback.

Uses camera position, FOV, orientation, and the vertical position of the
YOLO bounding box bottom edge to estimate person floor position.  No
assumption about person height (works for sitting and standing).

Depth model: the bbox bottom y-coordinate maps to a vertical angle from
the camera, which — combined with camera mounting height — gives floor
distance via  ``depth = cam_height / tan(angle)``.

Two projection methods:
1. Single camera: bearing from bbox x-position + depth from bbox y-position
2. Multi-camera triangulation: ray intersection from 2+ cameras seeing same person
"""
from __future__ import annotations

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

# Default camera mounting height (meters above floor)
_DEFAULT_CAM_HEIGHT_M = 2.5

# Default downward tilt angle (degrees below horizontal).
# Typical wall-mounted ESP32-CAM aimed at the room center.
_DEFAULT_TILT_DEG = 25.0

# Depth estimation bounds (floor-plane distance)
_MIN_DEPTH_M = 0.5
_MAX_DEPTH_M = 12.0

# Minimum bbox height in pixels to accept a detection
_MIN_BBOX_HEIGHT_PX = 15


class CameraProjector:
    """Project pixel detections to floor coordinates using camera geometry."""

    _instance: Optional[CameraProjector] = None

    @classmethod
    def get_instance(
        cls, cameras: dict | None = None
    ) -> CameraProjector:
        if cls._instance is None:
            cls._instance = cls(cameras or {})
        return cls._instance

    def __init__(self, cameras: dict):
        """
        Args:
            cameras: dict from config/spatial.yaml cameras section.
                     {camera_id: {position, fov_deg, orientation_deg, resolution,
                                  cam_height_m?, tilt_deg?}}
        """
        self._cameras: dict[str, dict] = {}
        for cam_id, cfg in cameras.items():
            pos = cfg.get("position")
            fov = cfg.get("fov_deg")
            if not pos or not fov:
                continue

            res = cfg.get("resolution", [640, 480])
            w, h = res[0], res[1]

            hfov_rad = math.radians(fov)
            vfov_rad = 2.0 * math.atan(math.tan(hfov_rad / 2.0) * h / w)

            self._cameras[cam_id] = {
                "position": [float(pos[0]), float(pos[1])],
                "fov_deg": float(fov),
                "orientation_deg": float(cfg.get("orientation_deg") or 0.0),
                "resolution": [w, h],
                "vfov_rad": vfov_rad,
                "cam_height_m": float(cfg.get("cam_height_m", _DEFAULT_CAM_HEIGHT_M)),
                "tilt_rad": math.radians(
                    float(cfg.get("tilt_deg", _DEFAULT_TILT_DEG))
                ),
            }

        logger.info("CameraProjector: %d cameras configured", len(self._cameras))

    def has_camera(self, camera_id: str) -> bool:
        return camera_id in self._cameras

    def project(
        self,
        camera_id: str,
        foot_px: list[float],
        bbox: list[float],
    ) -> Optional[list[float]]:
        """
        Project a single detection to floor coordinates.

        Args:
            camera_id: Camera identifier.
            foot_px: [x, y] foot point in pixels (bottom-center of bbox).
            bbox: [x1, y1, x2, y2] bounding box in pixels.

        Returns:
            [x_m, y_m] floor position, or None if camera not configured.
        """
        cam = self._cameras.get(camera_id)
        if cam is None:
            return None

        # Reject tiny detections (likely false positives)
        if (bbox[3] - bbox[1]) < _MIN_BBOX_HEIGHT_PX:
            return None

        bearing_rad = self._compute_bearing(cam, foot_px[0])
        depth_m = self._estimate_depth(cam, foot_px)
        if depth_m is None:
            return None

        cx, cy = cam["position"]
        floor_x = cx + depth_m * math.cos(bearing_rad)
        floor_y = cy + depth_m * math.sin(bearing_rad)
        return [round(floor_x, 2), round(floor_y, 2)]

    def compute_bearing(
        self, camera_id: str, px_x: float
    ) -> Optional[float]:
        """
        Compute bearing angle (radians) from camera to pixel x-coordinate.

        Convention: 0 = east (+x), counterclockwise positive (math standard).
        """
        cam = self._cameras.get(camera_id)
        if cam is None:
            return None
        return self._compute_bearing(cam, px_x)

    def get_camera_position(self, camera_id: str) -> Optional[list[float]]:
        cam = self._cameras.get(camera_id)
        return list(cam["position"]) if cam else None

    # ── Internal ──────────────────────────────────────────────────

    def _compute_bearing(self, cam: dict, px_x: float) -> float:
        """Absolute bearing from camera center-line to a pixel x-coordinate."""
        w = cam["resolution"][0]
        fov_deg = cam["fov_deg"]
        orient_deg = cam["orientation_deg"]

        # Fraction: -1 (left edge) to +1 (right edge)
        hfrac = (px_x - w / 2.0) / (w / 2.0)
        offset_deg = hfrac * (fov_deg / 2.0)

        return math.radians(orient_deg + offset_deg)

    def _estimate_depth(
        self, cam: dict, foot_px: list[float]
    ) -> Optional[float]:
        """
        Estimate floor-plane distance using the bbox bottom y-position.

        The vertical pixel position of the detection maps to a vertical angle
        from the camera.  Combined with the camera mounting height this gives
        floor distance:  ``depth = cam_height / tan(angle_below_horizontal)``

        This is independent of person height (works for sitting/standing).
        """
        h_img = cam["resolution"][1]
        y_bottom = foot_px[1]

        if y_bottom < 1:
            return None

        # Normalized vertical position: 0 = top of image, 1 = bottom
        y_norm = y_bottom / h_img

        tilt_rad = cam["tilt_rad"]
        vfov_rad = cam["vfov_rad"]

        # Angle from image center (positive = below center)
        angle_from_center = (y_norm - 0.5) * vfov_rad
        # Absolute angle below horizontal
        angle_below_horiz = tilt_rad + angle_from_center

        # Must be looking downward to see the floor
        if angle_below_horiz <= 0.02:  # ~1 degree guard
            return _MAX_DEPTH_M

        depth = cam["cam_height_m"] / math.tan(angle_below_horiz)
        return max(_MIN_DEPTH_M, min(depth, _MAX_DEPTH_M))

    def get_fov_center(self, camera_id: str) -> Optional[list[float]]:
        """
        Return the floor point at the center of the camera's FOV.

        Used as a last-resort fallback when both geometry projection and
        ArUco homography fail — places the person *somewhere* inside the
        camera's visible area rather than at [0,0].
        """
        cam = self._cameras.get(camera_id)
        if cam is None:
            return None
        w, h = cam["resolution"]
        center_px = [w / 2.0, h / 2.0]
        bearing_rad = self._compute_bearing(cam, center_px[0])
        depth_m = self._estimate_depth(cam, center_px)
        if depth_m is None:
            return None
        cx, cy = cam["position"]
        floor_x = cx + depth_m * math.cos(bearing_rad)
        floor_y = cy + depth_m * math.sin(bearing_rad)
        return [round(floor_x, 2), round(floor_y, 2)]

    # ── Multi-camera triangulation ────────────────────────────────

    @staticmethod
    def triangulate(
        pos_a: list[float],
        bearing_a: float,
        pos_b: list[float],
        bearing_b: float,
    ) -> Optional[list[float]]:
        """
        Triangulate floor position from two camera bearing rays.

        Solves the 2D ray intersection:
            pos_a + t * dir_a = pos_b + s * dir_b

        Args:
            pos_a, pos_b: Camera positions [x, y] in meters.
            bearing_a, bearing_b: Bearing angles in radians.

        Returns:
            [x_m, y_m] estimated position, or None if rays are parallel
            or intersection is behind a camera.
        """
        d_ax = math.cos(bearing_a)
        d_ay = math.sin(bearing_a)
        d_bx = math.cos(bearing_b)
        d_by = math.sin(bearing_b)

        # Determinant of the 2x2 system
        det = d_ax * (-d_by) - (-d_bx) * d_ay
        if abs(det) < 1e-6:
            return None  # Nearly parallel

        dx = pos_b[0] - pos_a[0]
        dy = pos_b[1] - pos_a[1]

        t = (dx * (-d_by) - (-d_bx) * dy) / det
        s = (d_ax * dy - d_ay * dx) / det

        # Person must be in front of both cameras
        if t < 0 or s < 0:
            return None

        # Average both ray endpoints for noise reduction
        pt_a_x = pos_a[0] + t * d_ax
        pt_a_y = pos_a[1] + t * d_ay
        pt_b_x = pos_b[0] + s * d_bx
        pt_b_y = pos_b[1] + s * d_by

        return [
            round((pt_a_x + pt_b_x) / 2.0, 2),
            round((pt_a_y + pt_b_y) / 2.0, 2),
        ]
