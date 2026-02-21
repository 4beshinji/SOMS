"""
Coordinate transformation utilities for person tracking.

- foot_from_bbox: Extract foot point from bounding box
- pixel_to_floor: Project pixel coords to floor meters via calibrator
- floor_distance: Euclidean distance in floor space
- point_in_zone: Check if a floor point is inside a zone polygon
"""
from __future__ import annotations

import math
from typing import Optional

import cv2
import numpy as np


def foot_from_bbox(bbox: list[float]) -> list[float]:
    """
    Extract foot-point (bottom-center) from a bounding box.

    Args:
        bbox: [x1, y1, x2, y2]

    Returns:
        [x, y] pixel coordinates of the foot point.
    """
    x1, y1, x2, y2 = bbox
    return [(x1 + x2) / 2.0, y2]


def pixel_to_floor(
    camera_id: str, pixel_xy: list[float]
) -> Optional[list[float]]:
    """
    Project pixel coordinates to floor-plane meters via ArucoCalibrator.

    Args:
        camera_id: Camera identifier.
        pixel_xy: [x, y] in pixel space.

    Returns:
        [x_m, y_m] in floor coordinates, or None if not calibrated.
    """
    from tracking.aruco_calibrator import ArucoCalibrator

    calibrator = ArucoCalibrator.get_instance()
    return calibrator.project_to_floor(camera_id, pixel_xy)


def floor_distance(a: list[float], b: list[float]) -> float:
    """
    Euclidean distance between two floor-plane points (meters).

    Args:
        a: [x_m, y_m]
        b: [x_m, y_m]

    Returns:
        Distance in meters.
    """
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return math.sqrt(dx * dx + dy * dy)


def point_in_zone(
    floor_xy: list[float], polygon: list[list[float]]
) -> bool:
    """
    Check if a floor-plane point lies inside a zone polygon.

    Args:
        floor_xy: [x_m, y_m] in floor coordinates.
        polygon: List of [x, y] vertices defining the zone boundary.

    Returns:
        True if the point is inside or on the boundary of the polygon.
    """
    if len(polygon) < 3:
        return False

    contour = np.array(polygon, dtype=np.float32).reshape(-1, 1, 2)
    result = cv2.pointPolygonTest(contour, tuple(floor_xy), measureDist=False)
    return result >= 0
