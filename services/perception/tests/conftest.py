"""Shared fixtures and helpers for perception service unit tests.

Key challenge: the ``tracking`` package's __init__.py imports all
submodules, including those that depend on cv2, torch, scipy, etc.
We must install mocks for these heavy dependencies *before* any
``from tracking.xxx import ...`` statement runs.
"""
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

# ── Path setup ──────────────────────────────────────────────────
_THIS_DIR = str(Path(__file__).resolve().parent)
PERCEPTION_SRC = str(Path(__file__).resolve().parent.parent / "src")

if PERCEPTION_SRC not in sys.path:
    sys.path.insert(0, PERCEPTION_SRC)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)


# ── Pre-install mocks for heavy dependencies ────────────────────
# These modules are imported at the top of various tracking/*.py files.
# Without GPU/ML packages installed, the imports would fail. We insert
# lightweight mocks into sys.modules so that ``import cv2`` etc. succeed.

def _ensure_mock(module_name: str) -> MagicMock:
    """Install a MagicMock into sys.modules if the real module is absent."""
    if module_name not in sys.modules:
        mock = MagicMock()
        sys.modules[module_name] = mock
        return mock
    return sys.modules[module_name]


# cv2 — used by aruco_calibrator, homography, reid_embedder
_mock_cv2 = _ensure_mock("cv2")
# Make cv2.aruco.DICT_4X4_50 a real int so getattr() works
_mock_cv2.aruco.DICT_4X4_50 = 0
# pointPolygonTest needs to return a float for homography.point_in_zone
_mock_cv2.pointPolygonTest = MagicMock(return_value=1.0)

# torch, torchvision — used by reid_embedder
_ensure_mock("torch")
_ensure_mock("torch.nn")
_ensure_mock("torch.nn.functional")
_ensure_mock("torchvision")
_ensure_mock("torchvision.transforms")

# torchreid — imported inside ReIDEmbedder.__init__
_ensure_mock("torchreid")
_ensure_mock("torchreid.models")

# scipy — used by cross_camera_tracker
_mock_scipy = _ensure_mock("scipy")
_mock_scipy_opt = _ensure_mock("scipy.optimize")
# linear_sum_assignment returns (row_ind, col_ind)
_mock_scipy_opt.linear_sum_assignment = MagicMock(
    return_value=(np.array([], dtype=int), np.array([], dtype=int))
)


# ── Common test helpers ──────────────────────────────────────────


def make_embedding(dim: int = 512, seed: int | None = None) -> np.ndarray:
    """Create a random L2-normalized embedding vector."""
    rng = np.random.RandomState(seed)
    vec = rng.randn(dim).astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def make_tracked_person(
    track_id: int = 1,
    camera_id: str = "cam_01",
    bbox_px: list[float] | None = None,
    foot_px: list[float] | None = None,
    foot_floor: list[float] | None = None,
    confidence: float = 0.9,
    reid_embedding: np.ndarray | None = None,
    timestamp: float = 1000.0,
):
    """Create a TrackedPerson instance for testing."""
    from tracking.tracklet import TrackedPerson

    if bbox_px is None:
        bbox_px = [100.0, 200.0, 200.0, 400.0]
    if foot_px is None:
        foot_px = [150.0, 400.0]
    if foot_floor is None:
        foot_floor = [2.0, 3.0]
    if reid_embedding is None:
        reid_embedding = make_embedding(seed=track_id)

    return TrackedPerson(
        track_id=track_id,
        camera_id=camera_id,
        bbox_px=bbox_px,
        foot_px=foot_px,
        foot_floor=foot_floor,
        confidence=confidence,
        reid_embedding=reid_embedding,
        timestamp=timestamp,
    )


def make_wifi_tracked_person(
    track_id: int = 1,
    node_id: str = "wifi_01",
    foot_floor: list[float] | None = None,
    confidence: float = 0.5,
    timestamp: float = 1000.0,
):
    """Create a WiFi-sourced TrackedPerson for testing.

    WiFi detections have zero-vector embeddings, empty bboxes,
    and source_type='wifi'.
    """
    from tracking.tracklet import TrackedPerson

    if foot_floor is None:
        foot_floor = [5.0, 5.0]

    return TrackedPerson(
        track_id=track_id,
        camera_id=node_id,
        bbox_px=[0.0, 0.0, 0.0, 0.0],
        foot_px=[0.0, 0.0],
        foot_floor=foot_floor,
        confidence=confidence,
        reid_embedding=np.zeros(512, dtype=np.float32),
        timestamp=timestamp,
        source_type="wifi",
    )
