"""CSI raw data preprocessor — Hampel filter + spectrogram generation.

Converts raw CSI amplitude/phase arrays from ESP32-S3 into CNN-ready
spectrogram tensors.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass
class CSIFrame:
    """Single CSI measurement from one WiFi node."""
    node_id: str
    timestamp: float
    amplitudes: np.ndarray   # shape: (n_subcarriers,)
    zone: str = ""


class CSIProcessor:
    """Preprocesses CSI data: Hampel outlier filter + sliding-window spectrogram."""

    def __init__(
        self,
        subcarrier_count: int = 52,
        hampel_window: int = 5,
        hampel_threshold: float = 3.0,
        spectrogram_window_sec: float = 1.0,
        sample_rate_hz: float = 100.0,
    ):
        self._n_sub = subcarrier_count
        self._hampel_window = hampel_window
        self._hampel_threshold = hampel_threshold
        self._window_sec = spectrogram_window_sec
        self._sample_rate = sample_rate_hz

        # Per-node sliding buffers: node_id -> deque of (timestamp, amplitudes)
        self._buffers: dict[str, deque] = {}
        self._max_samples = int(spectrogram_window_sec * sample_rate_hz)

    def add_frame(self, frame: CSIFrame) -> np.ndarray | None:
        """
        Add a CSI frame and return a spectrogram if the window is full.

        Returns:
            np.ndarray of shape (n_subcarriers, time_steps) or None if
            the sliding window is not yet full.
        """
        if frame.amplitudes.shape[0] != self._n_sub:
            return None

        # Hampel filter on incoming amplitudes
        filtered = self._hampel_filter(frame.node_id, frame.amplitudes)

        if frame.node_id not in self._buffers:
            self._buffers[frame.node_id] = deque(maxlen=self._max_samples)

        buf = self._buffers[frame.node_id]
        buf.append((frame.timestamp, filtered))

        if len(buf) < self._max_samples:
            return None

        # Build spectrogram: (n_subcarriers, time_steps)
        return np.column_stack([amp for _, amp in buf])

    def _hampel_filter(self, node_id: str, values: np.ndarray) -> np.ndarray:
        """Simple per-subcarrier Hampel outlier replacement."""
        buf = self._buffers.get(node_id)
        if buf is None or len(buf) < self._hampel_window:
            return values.copy()

        # Get recent window of amplitudes
        recent = np.array([amp for _, amp in list(buf)[-self._hampel_window:]])
        median = np.median(recent, axis=0)
        mad = np.median(np.abs(recent - median), axis=0)
        mad = np.maximum(mad, 1e-10)

        result = values.copy()
        outliers = np.abs(values - median) / mad > self._hampel_threshold
        result[outliers] = median[outliers]
        return result

    def reset(self, node_id: str | None = None):
        """Clear buffers for a node or all nodes."""
        if node_id:
            self._buffers.pop(node_id, None)
        else:
            self._buffers.clear()
