"""WiFi CSI pose estimator — CNN wrapper with mock support.

Abstracts the CNN model that converts CSI spectrograms into floor-plane
(x, y) position estimates. Supports a mock mode for testing without
a trained model.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PoseEstimate:
    """Single position estimate from WiFi CSI."""
    x: float
    y: float
    confidence: float
    person_id: int = 0


class WifiPoseEstimator:
    """Estimates person positions from CSI spectrograms."""

    def __init__(self, model_type: str = "mock", model_path: str | None = None):
        self._model_type = model_type
        self._model = None

        if model_type == "cnn" and model_path:
            self._load_model(model_path)
        else:
            logger.info("WifiPoseEstimator using mock mode")

    def _load_model(self, path: str):
        """Load a trained CNN model."""
        try:
            import torch
            self._model = torch.jit.load(path, map_location="cpu")
            self._model.eval()
            logger.info("Loaded WiFi pose model from %s", path)
        except Exception as e:
            logger.warning("Failed to load model %s: %s — falling back to mock", path, e)
            self._model_type = "mock"

    def predict(self, spectrogram: np.ndarray, zone: str = "") -> list[PoseEstimate]:
        """
        Predict person positions from a CSI spectrogram.

        Args:
            spectrogram: shape (n_subcarriers, time_steps)
            zone: Zone hint for context.

        Returns:
            List of PoseEstimate (may be empty if no person detected).
        """
        if self._model_type == "mock":
            return self._mock_predict(spectrogram)
        return self._cnn_predict(spectrogram)

    def _mock_predict(self, spectrogram: np.ndarray) -> list[PoseEstimate]:
        """Mock prediction: returns a single person at a position derived from CSI energy."""
        energy = np.mean(np.abs(spectrogram))
        if energy < 0.01:
            return []

        # Derive a pseudo-position from spectral features
        n_sub = spectrogram.shape[0]
        weights = np.arange(n_sub, dtype=np.float64)
        col_energy = np.mean(np.abs(spectrogram), axis=1)
        total = col_energy.sum()
        if total < 1e-10:
            return []

        centroid = float(np.dot(weights, col_energy) / total)
        x = centroid / n_sub * 10.0  # Scale to ~10m range
        y = float(np.std(spectrogram)) * 5.0

        return [PoseEstimate(x=x, y=y, confidence=min(energy, 1.0), person_id=1)]

    def _cnn_predict(self, spectrogram: np.ndarray) -> list[PoseEstimate]:
        """Run CNN inference on the spectrogram."""
        import torch

        tensor = torch.from_numpy(spectrogram).unsqueeze(0).unsqueeze(0).float()
        with torch.no_grad():
            output = self._model(tensor)

        # Expected output: (batch, n_persons, 3) — [x, y, confidence]
        results = output.squeeze(0).numpy()
        estimates = []
        for i, row in enumerate(results):
            if row[2] > 0.3:  # Confidence threshold
                estimates.append(PoseEstimate(
                    x=float(row[0]),
                    y=float(row[1]),
                    confidence=float(row[2]),
                    person_id=i + 1,
                ))
        return estimates
