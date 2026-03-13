"""Shared fixtures for wifi-pose service tests."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

# Path setup
WIFI_POSE_SRC = str(Path(__file__).resolve().parent.parent / "src")
if WIFI_POSE_SRC not in sys.path:
    sys.path.insert(0, WIFI_POSE_SRC)

# Mock cv2 for environments without OpenCV
_mock_cv2 = MagicMock()
if "cv2" not in sys.modules:
    sys.modules["cv2"] = _mock_cv2
    _mock_cv2.RANSAC = 8
    # estimateAffinePartial2D returns (transform, inliers)
    _mock_cv2.estimateAffinePartial2D = MagicMock(
        return_value=(np.eye(2, 3, dtype=np.float64), np.ones((10, 1), dtype=np.uint8))
    )
    _mock_cv2.transform = MagicMock(
        side_effect=lambda pt, M: np.array([[[
            M[0, 0] * pt[0, 0, 0] + M[0, 1] * pt[0, 0, 1] + M[0, 2],
            M[1, 0] * pt[0, 0, 0] + M[1, 1] * pt[0, 0, 1] + M[1, 2],
        ]]])
    )
