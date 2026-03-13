"""
WiFi-YOLO cross-modal calibrator — learns an affine transform from
WiFi raw coordinates to YOLO floor coordinates using paired observations.

Follows the ArucoCalibrator singleton/cache pattern from the perception service.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CalibrationPair:
    """A paired WiFi + YOLO observation for calibration."""
    wifi_xy: list[float]
    yolo_xy: list[float]
    timestamp: float
    zone: str
    confidence: float


class WifiCalibrator:
    """Learns per-zone affine transforms from WiFi→YOLO coordinate pairs."""

    _instance: Optional[WifiCalibrator] = None

    @classmethod
    def get_instance(
        cls,
        cache_path: str | None = None,
        sliding_window_size: int = 200,
        min_pairs: int = 20,
    ) -> WifiCalibrator:
        if cls._instance is None:
            cls._instance = cls(cache_path, sliding_window_size, min_pairs)
        return cls._instance

    def __init__(
        self,
        cache_path: str | None = None,
        sliding_window_size: int = 200,
        min_pairs: int = 20,
    ):
        self._cache_path = Path(cache_path) if cache_path else None
        self._window_size = sliding_window_size
        self._min_pairs = min_pairs

        # Per-zone sliding window of calibration pairs
        self._pairs: dict[str, deque[CalibrationPair]] = {}

        # Per-zone affine transform: zone -> 2x3 np.ndarray
        self._transforms: dict[str, np.ndarray] = {}

        self._load_cache()

        logger.info(
            "WifiCalibrator initialized: min_pairs=%d, window=%d",
            min_pairs, sliding_window_size,
        )

    def add_pair(self, pair: CalibrationPair):
        """Add a calibration pair and attempt recalibration."""
        zone = pair.zone
        if zone not in self._pairs:
            self._pairs[zone] = deque(maxlen=self._window_size)
        self._pairs[zone].append(pair)

        # Attempt calibration if we have enough pairs
        if len(self._pairs[zone]) >= self._min_pairs:
            self.try_calibrate(zone)

    def try_calibrate(self, zone: str) -> bool:
        """Compute affine transform for a zone using RANSAC."""
        pairs = self._pairs.get(zone)
        if not pairs or len(pairs) < self._min_pairs:
            return False

        src = np.array([[p.wifi_xy[0], p.wifi_xy[1]] for p in pairs], dtype=np.float64)
        dst = np.array([[p.yolo_xy[0], p.yolo_xy[1]] for p in pairs], dtype=np.float64)

        transform, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC)
        if transform is None:
            logger.warning("Affine estimation failed for zone %s", zone)
            return False

        n_inliers = int(inliers.sum()) if inliers is not None else len(pairs)
        self._transforms[zone] = transform
        self._save_cache()

        logger.info(
            "Calibrated zone %s: %d/%d inliers, transform=\n%s",
            zone, n_inliers, len(pairs), transform,
        )
        return True

    def correct(self, zone: str, wifi_xy: list[float]) -> list[float]:
        """Apply affine correction to WiFi raw coordinates."""
        transform = self._transforms.get(zone)
        if transform is None:
            return wifi_xy  # Pass through uncorrected

        pt = np.array([[wifi_xy]], dtype=np.float64)  # shape (1, 1, 2)
        corrected = cv2.transform(pt, transform)
        return [float(corrected[0, 0, 0]), float(corrected[0, 0, 1])]

    def has_calibration(self, zone: str) -> bool:
        return zone in self._transforms

    def get_calibrated_zones(self) -> list[str]:
        return list(self._transforms.keys())

    def _load_cache(self):
        """Load cached affine transforms from disk."""
        if not self._cache_path or not self._cache_path.exists():
            return
        try:
            data = json.loads(self._cache_path.read_text())
            for zone, t_list in data.items():
                self._transforms[zone] = np.array(t_list, dtype=np.float64)
            logger.info("Loaded calibration cache: %d zones", len(self._transforms))
        except Exception as e:
            logger.warning("Failed to load calibration cache: %s", e)

    def _save_cache(self):
        """Persist affine transforms to disk."""
        if not self._cache_path:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                zone: t.tolist()
                for zone, t in self._transforms.items()
            }
            self._cache_path.write_text(json.dumps(data, indent=2))
            logger.info("Saved calibration cache: %d zones", len(data))
        except Exception as e:
            logger.warning("Failed to save calibration cache: %s", e)
