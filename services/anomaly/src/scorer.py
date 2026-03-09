"""Anomaly score computation with cooldown management."""
import time
from dataclasses import dataclass, field

import numpy as np
from loguru import logger

from config import settings


@dataclass
class AnomalyResult:
    zone: str
    channel: str
    score: float
    predicted: float
    actual: float
    severity: str
    source: str = "batch"


class Scorer:
    COOLDOWN_SECONDS = 3600  # 1 hour

    def __init__(
        self,
        warning_threshold: float | None = None,
        critical_threshold: float | None = None,
    ):
        self.warning_threshold = warning_threshold or settings.WARNING_THRESHOLD
        self.critical_threshold = critical_threshold or settings.CRITICAL_THRESHOLD
        self._last_alert: dict[str, float] = {}  # "zone:channel" → timestamp

    def compute_scores(
        self,
        predicted: np.ndarray,
        actual: np.ndarray,
        train_stds: np.ndarray,
        zone: str,
        channels: list[str],
        source: str = "batch",
    ) -> list[AnomalyResult]:
        """Compute anomaly scores for predicted vs actual values.

        Args:
            predicted: (n_targets,) predicted avg values (z-scored)
            actual: (n_targets,) actual avg values (z-scored)
            train_stds: (n_targets,) training std per channel (for de-normalization context)
            zone: zone identifier
            channels: channel names matching the target indices
            source: "batch" or "realtime"

        Returns:
            List of AnomalyResult for channels exceeding threshold
        """
        results = []
        for i, channel in enumerate(channels):
            if i >= len(predicted) or i >= len(actual):
                continue

            std = train_stds[i] if train_stds[i] > 0 else 1.0
            score = abs(float(actual[i]) - float(predicted[i])) / std

            severity = self._classify_severity(score)
            if severity is None:
                continue

            cooldown_key = f"{zone}:{channel}"
            if self._is_in_cooldown(cooldown_key):
                continue

            self._last_alert[cooldown_key] = time.time()

            results.append(
                AnomalyResult(
                    zone=zone,
                    channel=channel,
                    score=round(score, 2),
                    predicted=round(float(predicted[i]), 2),
                    actual=round(float(actual[i]), 2),
                    severity=severity,
                    source=source,
                )
            )

        return results

    def _classify_severity(self, score: float) -> str | None:
        if score >= self.critical_threshold:
            return "critical"
        elif score >= self.warning_threshold:
            return "warning"
        return None

    def _is_in_cooldown(self, key: str) -> bool:
        last = self._last_alert.get(key)
        if last is None:
            return False
        return (time.time() - last) < self.COOLDOWN_SECONDS

    def clear_cooldown(self, zone: str | None = None, channel: str | None = None):
        """Clear cooldown for testing or manual reset."""
        if zone is None:
            self._last_alert.clear()
        elif channel is None:
            keys = [k for k in self._last_alert if k.startswith(f"{zone}:")]
            for k in keys:
                del self._last_alert[k]
        else:
            self._last_alert.pop(f"{zone}:{channel}", None)
