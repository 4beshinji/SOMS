"""AI-VAD: Attribute-based Video Anomaly Detection.

Combines three feature streams per detected person:
  1. Velocity: speed + direction from bbox displacement
  2. Pose: normalized skeleton geometry
  3. Appearance: deep feature vector from person crop (simplified CNN)

Anomaly = distance from normal distribution in each feature space,
fused into a single score.

Reference: Reiss et al., "Attribute-Based Representations for Accurate
and Interpretable Video Anomaly Detection" (arXiv 2212.00789)
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


@dataclass
class PersonAttributes:
    person_id: int
    velocity: np.ndarray          # (2,) dx, dy per second
    speed: float                  # pixels/second
    direction: float              # radians
    pose_features: np.ndarray     # (34,) flattened normalized keypoints
    appearance_features: np.ndarray | None  # (64,) deep features from crop


if TORCH_AVAILABLE:

    class AppearanceEncoder(nn.Module):
        """Lightweight CNN for person crop feature extraction.

        Input: (3, 128, 64) person crop → 64-dim feature vector.
        ~30K params.
        """

        def __init__(self, out_dim: int = 64):
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(3, 16, 3, stride=2, padding=1),  # 64x32
                nn.ReLU(),
                nn.Conv2d(16, 32, 3, stride=2, padding=1),  # 32x16
                nn.ReLU(),
                nn.Conv2d(32, 64, 3, stride=2, padding=1),  # 16x8
                nn.ReLU(),
                nn.AdaptiveAvgPool2d((1, 1)),
            )
            self.fc = nn.Linear(64, out_dim)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """(B, 3, 128, 64) → (B, out_dim)"""
            h = self.features(x).flatten(1)
            return F.normalize(self.fc(h), dim=-1)


class GaussianDensity:
    """Simple Gaussian density estimator for anomaly scoring."""

    def __init__(self, dim: int):
        self.dim = dim
        self.mean = np.zeros(dim)
        self.cov_inv = np.eye(dim)
        self._fitted = False

    def fit(self, data: np.ndarray):
        """Fit from (N, dim) normal data."""
        if data.shape[0] < 2:
            return
        self.mean = np.mean(data, axis=0)
        cov = np.cov(data, rowvar=False)
        # Regularize
        cov += np.eye(self.dim) * 1e-4
        self.cov_inv = np.linalg.inv(cov)
        self._fitted = True

    def score(self, x: np.ndarray) -> float:
        """Mahalanobis distance from the fitted normal distribution."""
        if not self._fitted:
            return 0.0
        diff = x - self.mean
        return float(np.sqrt(diff @ self.cov_inv @ diff))

    def save(self) -> dict:
        return {
            "mean": self.mean.tolist(),
            "cov_inv": self.cov_inv.tolist(),
            "fitted": self._fitted,
        }

    def load(self, data: dict):
        self.mean = np.array(data["mean"])
        self.cov_inv = np.array(data["cov_inv"])
        self._fitted = data.get("fitted", True)


class AttributeVADDetector:
    """Manages per-person attribute extraction and anomaly scoring."""

    VELOCITY_DIM = 3   # speed, dx_norm, dy_norm
    POSE_DIM = 34       # 17 joints × 2 coords (normalized)
    APPEARANCE_DIM = 64

    def __init__(
        self,
        model_path: str | None = None,
        device: str = "cpu",
        velocity_weight: float = 0.3,
        pose_weight: float = 0.4,
        appearance_weight: float = 0.3,
    ):
        self._device = device
        self._weights = {
            "velocity": velocity_weight,
            "pose": pose_weight,
            "appearance": appearance_weight,
        }

        # Per-person tracking for velocity computation
        self._prev_positions: dict[int, tuple[float, float, float]] = {}  # id → (cx, cy, ts)

        # Density estimators (fitted on normal data)
        self._velocity_density = GaussianDensity(self.VELOCITY_DIM)
        self._pose_density = GaussianDensity(self.POSE_DIM)
        self._appearance_density = GaussianDensity(self.APPEARANCE_DIM)

        # Appearance encoder
        self._encoder: AppearanceEncoder | None = None
        if TORCH_AVAILABLE:
            try:
                self._encoder = AppearanceEncoder(self.APPEARANCE_DIM)
                self._encoder.to(device)
                self._encoder.eval()
            except Exception:
                self._encoder = None

        if model_path and os.path.exists(model_path):
            self._load(model_path)

    def extract_attributes(
        self,
        person_id: int,
        bbox: list[float],
        keypoints: np.ndarray | None,
        confidences: np.ndarray | None,
        frame: np.ndarray | None,
        timestamp: float,
    ) -> PersonAttributes | None:
        """Extract velocity, pose, and appearance attributes for one person."""
        x1, y1, x2, y2 = bbox
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

        # --- Velocity ---
        velocity = np.zeros(2)
        speed = 0.0
        if person_id in self._prev_positions:
            px, py, pt = self._prev_positions[person_id]
            dt = timestamp - pt
            if dt > 0.01:
                velocity = np.array([(cx - px) / dt, (cy - py) / dt])
                speed = float(np.linalg.norm(velocity))
        self._prev_positions[person_id] = (cx, cy, timestamp)

        direction = float(np.arctan2(velocity[1], velocity[0])) if speed > 1.0 else 0.0
        vel_norm = velocity / max(speed, 1e-6)
        velocity_features = np.array([speed, vel_norm[0], vel_norm[1]])

        # --- Pose ---
        pose_features = np.zeros(self.POSE_DIM)
        if keypoints is not None and confidences is not None:
            L_HIP, R_HIP = 11, 12
            if confidences[L_HIP] > 0.3 and confidences[R_HIP] > 0.3:
                hip_center = (keypoints[L_HIP] + keypoints[R_HIP]) / 2.0
                scale = max(y2 - y1, 1.0)
                for i in range(17):
                    if confidences[i] > 0.3:
                        pose_features[i * 2] = (keypoints[i, 0] - hip_center[0]) / scale
                        pose_features[i * 2 + 1] = (keypoints[i, 1] - hip_center[1]) / scale

        # --- Appearance ---
        appearance_features = None
        if frame is not None and self._encoder is not None and TORCH_AVAILABLE:
            appearance_features = self._extract_appearance(frame, bbox)

        return PersonAttributes(
            person_id=person_id,
            velocity=velocity_features,
            speed=speed,
            direction=direction,
            pose_features=pose_features,
            appearance_features=appearance_features,
        )

    def score(self, attrs: PersonAttributes) -> dict[str, float]:
        """Score attributes against normal distributions.

        Returns:
            dict with per-stream scores and combined score
        """
        vel_score = self._velocity_density.score(attrs.velocity)
        pose_score = self._pose_density.score(attrs.pose_features)

        app_score = 0.0
        if attrs.appearance_features is not None:
            app_score = self._appearance_density.score(attrs.appearance_features)

        combined = (
            self._weights["velocity"] * vel_score
            + self._weights["pose"] * pose_score
            + self._weights["appearance"] * app_score
        )

        return {
            "velocity": round(vel_score, 2),
            "pose": round(pose_score, 2),
            "appearance": round(app_score, 2),
            "combined": round(combined, 2),
        }

    def evict(self, person_id: int):
        """Remove tracking state for departed person."""
        self._prev_positions.pop(person_id, None)

    def _extract_appearance(self, frame: np.ndarray, bbox: list[float]) -> np.ndarray:
        """Crop person from frame and extract features."""
        import cv2

        h, w = frame.shape[:2]
        x1 = max(0, int(bbox[0]))
        y1 = max(0, int(bbox[1]))
        x2 = min(w, int(bbox[2]))
        y2 = min(h, int(bbox[3]))

        if x2 - x1 < 4 or y2 - y1 < 4:
            return np.zeros(self.APPEARANCE_DIM)

        crop = frame[y1:y2, x1:x2]
        crop = cv2.resize(crop, (64, 128))
        tensor = torch.FloatTensor(crop).permute(2, 0, 1).unsqueeze(0) / 255.0
        tensor = tensor.to(self._device)

        with torch.no_grad():
            features = self._encoder(tensor)
        return features.cpu().numpy().flatten()

    def _load(self, path: str):
        """Load density models and appearance encoder."""
        import json

        try:
            checkpoint = {}
            if TORCH_AVAILABLE:
                checkpoint = torch.load(path, map_location=self._device, weights_only=False)
                if "encoder_state_dict" in checkpoint and self._encoder:
                    self._encoder.load_state_dict(checkpoint["encoder_state_dict"])
            # Load density estimators
            if "densities" in checkpoint:
                d = checkpoint["densities"]
                if "velocity" in d:
                    self._velocity_density.load(d["velocity"])
                if "pose" in d:
                    self._pose_density.load(d["pose"])
                if "appearance" in d:
                    self._appearance_density.load(d["appearance"])
            logger.info("Loaded AttributeVAD model from %s", path)
        except Exception as e:
            logger.warning("Failed to load AttributeVAD model: %s", e)

    def save(self, path: str):
        """Save density models and appearance encoder."""
        checkpoint = {
            "densities": {
                "velocity": self._velocity_density.save(),
                "pose": self._pose_density.save(),
                "appearance": self._appearance_density.save(),
            },
        }
        if TORCH_AVAILABLE and self._encoder:
            checkpoint["encoder_state_dict"] = self._encoder.state_dict()
        torch.save(checkpoint, path)
