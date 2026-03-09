"""Realtime anomaly detection from MQTT raw sensor readings."""
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import numpy as np
import torch
from loguru import logger

from config import settings
from data.preprocessor import Preprocessor
from mqtt_client import AnomalyMQTTClient
from scorer import AnomalyResult, Scorer


class RealtimeDetector:
    def __init__(
        self,
        models: dict,  # zone → (model, norm_stats)
        preprocessor: Preprocessor,
        scorer: Scorer,
        mqtt_client: AnomalyMQTTClient,
    ):
        self._models = models
        self._preprocessor = preprocessor
        self._scorer = scorer
        self._mqtt = mqtt_client
        self._buffers: dict[str, dict[str, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=settings.REALTIME_BUFFER_MIN))
        )
        self._last_check: dict[str, float] = {}
        self._check_interval = 60  # check at most every 60 seconds per zone

    def on_sensor_message(self, zone: str, channel: str, value: float):
        """Called when a raw sensor MQTT message arrives."""
        now = time.time()
        ts = datetime.fromtimestamp(now, tz=timezone.utc)
        self._buffers[zone][channel].append((ts, value))

        # Rate-limit checks per zone
        last = self._last_check.get(zone, 0)
        if now - last < self._check_interval:
            return

        if zone not in self._models:
            return

        self._last_check[zone] = now
        self._check_anomaly(zone)

    def _check_anomaly(self, zone: str):
        """Check for anomalies using buffered readings."""
        if zone not in self._models:
            return

        model, norm_stats = self._models[zone]
        zone_buffer = self._buffers[zone]

        # Build hourly features from buffer
        features = self._preprocessor.raw_to_hourly_features(dict(zone_buffer))

        # Get training stds for scoring (avg stats only, indices 0, 3, 6, ...)
        train_stds = np.ones(Preprocessor.N_TARGETS)
        for i, channel in enumerate(Preprocessor.CHANNELS):
            key = f"avg_{channel}"
            if key in norm_stats and norm_stats[key]["std"] > 0:
                train_stds[i] = norm_stats[key]["std"]

        # Normalize features using training stats
        means = np.zeros(Preprocessor.N_SENSOR_FEATURES)
        stds = np.ones(Preprocessor.N_SENSOR_FEATURES)
        for i, channel in enumerate(Preprocessor.CHANNELS):
            for j, stat in enumerate(Preprocessor.STATS):
                key = f"{stat}_{channel}"
                idx = i * len(Preprocessor.STATS) + j
                if key in norm_stats:
                    means[idx] = norm_stats[key]["mean"]
                    stds[idx] = norm_stats[key]["std"] if norm_stats[key]["std"] > 0 else 1.0

        # Fill NaN and normalize
        features_clean = self._preprocessor.fill_gaps(features)
        features_norm = (features_clean - means) / stds

        # Add temporal features
        now = datetime.now(timezone.utc)
        temporal = self._preprocessor.add_temporal([now])
        full_features = np.concatenate([features_norm, temporal], axis=1)

        # Pad to window size (fill with zeros for missing history)
        window = settings.WINDOW_SIZE
        padded = np.zeros((1, window, Preprocessor.N_FEATURES))
        padded[0, -1, :] = full_features[0]

        # Run inference
        try:
            model.eval()
            with torch.no_grad():
                x = torch.FloatTensor(padded)
                pred = model(x)  # (1, horizon, n_targets)

            # Compare prediction for next step with current actual values
            predicted = pred[0, 0, :].numpy()  # first horizon step

            # Get actual avg values from buffer
            actual = np.full(Preprocessor.N_TARGETS, np.nan)
            for i, channel in enumerate(Preprocessor.CHANNELS):
                readings = zone_buffer.get(channel, deque())
                if readings:
                    values = [v for _, v in readings]
                    # Normalize actual to z-score space
                    key = f"avg_{channel}"
                    if key in norm_stats and norm_stats[key]["std"] > 0:
                        actual[i] = (np.mean(values) - norm_stats[key]["mean"]) / norm_stats[key]["std"]

            if np.any(np.isnan(actual)):
                return

            results = self._scorer.compute_scores(
                predicted=predicted,
                actual=actual,
                train_stds=np.ones(Preprocessor.N_TARGETS),  # Already in z-score space
                zone=zone,
                channels=Preprocessor.CHANNELS,
                source="realtime",
            )

            for result in results:
                self._mqtt.publish_anomaly(result)

        except Exception as e:
            logger.debug("Realtime inference failed for zone {}: {}", zone, e)

    def update_model(self, zone: str, model, norm_stats: dict):
        """Update the model for a zone (after retraining)."""
        self._models[zone] = (model, norm_stats)
