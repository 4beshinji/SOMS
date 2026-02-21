"""
MTMC (Multi-Target Multi-Camera) person tracking package.

Provides ArUco-based camera calibration, single-camera tracking (SCT)
via BoT-SORT, ReID feature extraction, and cross-camera track association.
"""
from tracking.tracklet import TrackedPerson, Tracklet, GlobalTrack
from tracking.aruco_calibrator import ArucoCalibrator
from tracking.homography import foot_from_bbox, pixel_to_floor, floor_distance, point_in_zone
from tracking.reid_embedder import ReIDEmbedder
from tracking.cross_camera_tracker import CrossCameraTracker
from tracking.mtmc_publisher import MTMCPublisher

__all__ = [
    "TrackedPerson",
    "Tracklet",
    "GlobalTrack",
    "ArucoCalibrator",
    "foot_from_bbox",
    "pixel_to_floor",
    "floor_distance",
    "point_in_zone",
    "ReIDEmbedder",
    "CrossCameraTracker",
    "MTMCPublisher",
]
