"""Preprocess time series data for model training and inference."""
import math
from datetime import datetime

import numpy as np


class Preprocessor:
    CHANNELS = [
        "temperature",
        "humidity",
        "co2",
        "illuminance",
        "pressure",
        "gas_resistance",
    ]
    STATS = ["avg", "max", "min"]
    # 6 channels × 3 stats = 18 sensor features + 4 temporal = 22 total
    N_SENSOR_FEATURES = len(CHANNELS) * len(STATS)
    N_TEMPORAL_FEATURES = 4
    N_FEATURES = N_SENSOR_FEATURES + N_TEMPORAL_FEATURES
    # Target: 6 channels avg only
    N_TARGETS = len(CHANNELS)

    def series_to_array(self, series: list[dict]) -> tuple[np.ndarray, list[datetime]]:
        """Convert list of hourly dicts to feature array.

        Returns:
            (data, timestamps): data is (T, 18) sensor features, timestamps for temporal encoding
        """
        T = len(series)
        data = np.full((T, self.N_SENSOR_FEATURES), np.nan)
        timestamps = []

        for i, entry in enumerate(series):
            ts = entry.get("timestamp")
            timestamps.append(ts)
            for j, channel in enumerate(self.CHANNELS):
                for k, stat in enumerate(self.STATS):
                    key = f"{stat}_{channel}"
                    val = entry.get(key)
                    if val is not None:
                        data[i, j * len(self.STATS) + k] = float(val)

        return data, timestamps

    @staticmethod
    def fill_gaps(data: np.ndarray) -> np.ndarray:
        """Fill NaN gaps with linear interpolation, then forward/backward fill."""
        result = data.copy()
        for col in range(result.shape[1]):
            series = result[:, col]
            valid = ~np.isnan(series)
            if valid.sum() == 0:
                result[:, col] = 0.0
                continue
            if valid.sum() == len(series):
                continue
            indices = np.arange(len(series))
            result[:, col] = np.interp(indices, indices[valid], series[valid])
        return result

    @staticmethod
    def add_temporal(timestamps: list[datetime]) -> np.ndarray:
        """Encode timestamps as sin/cos features: hour_sin, hour_cos, dow_sin, dow_cos."""
        T = len(timestamps)
        temporal = np.zeros((T, 4))
        for i, ts in enumerate(timestamps):
            if hasattr(ts, "hour"):
                hour = ts.hour
                dow = ts.weekday()
            else:
                hour = 0
                dow = 0
            temporal[i, 0] = math.sin(2 * math.pi * hour / 24)
            temporal[i, 1] = math.cos(2 * math.pi * hour / 24)
            temporal[i, 2] = math.sin(2 * math.pi * dow / 7)
            temporal[i, 3] = math.cos(2 * math.pi * dow / 7)
        return temporal

    @staticmethod
    def normalize(
        data: np.ndarray, means: np.ndarray | None = None, stds: np.ndarray | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Z-score normalization. If means/stds not provided, compute from data."""
        if means is None:
            means = np.nanmean(data, axis=0)
        if stds is None:
            stds = np.nanstd(data, axis=0)
        # Avoid division by zero
        stds_safe = np.where(stds == 0, 1.0, stds)
        normalized = (data - means) / stds_safe
        return normalized, means, stds

    @staticmethod
    def create_windows(
        data: np.ndarray, window: int = 168, horizon: int = 6
    ) -> tuple[np.ndarray, np.ndarray]:
        """Create sliding windows for training.

        Args:
            data: (T, F) array of all features (22-dim)
            window: input window size (default 168 = 1 week)
            horizon: prediction horizon (default 6 hours)

        Returns:
            X: (N, window, F) input windows
            Y: (N, horizon, 6) target windows (avg values of 6 channels only)
        """
        T, F = data.shape
        n_samples = T - window - horizon + 1
        if n_samples <= 0:
            return np.empty((0, window, F)), np.empty((0, horizon, 6))

        X = np.zeros((n_samples, window, F))
        Y = np.zeros((n_samples, horizon, 6))

        for i in range(n_samples):
            X[i] = data[i : i + window]
            # Target: avg values (index 0, 3, 6, 9, 12, 15 in sensor features)
            for ch in range(6):
                avg_idx = ch * 3  # avg is first stat for each channel
                Y[i, :, ch] = data[i + window : i + window + horizon, avg_idx]

        return X, Y

    def raw_to_hourly_features(
        self, raw_buffer: dict[str, list[tuple[datetime, float]]]
    ) -> np.ndarray:
        """Convert raw MQTT readings buffer to a single hourly feature vector.

        Args:
            raw_buffer: {channel: [(timestamp, value), ...]} for one zone

        Returns:
            (1, 18) array of avg/max/min per channel
        """
        features = np.full((1, self.N_SENSOR_FEATURES), np.nan)
        for i, channel in enumerate(self.CHANNELS):
            readings = raw_buffer.get(channel, [])
            if not readings:
                continue
            values = [v for _, v in readings]
            base = i * len(self.STATS)
            features[0, base] = np.mean(values)  # avg
            features[0, base + 1] = np.max(values)  # max
            features[0, base + 2] = np.min(values)  # min
        return features

    def prepare_training_data(
        self, series: list[dict], window: int = 168, horizon: int = 6
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
        """Full pipeline: series → arrays → fill → normalize → windows.

        Returns:
            (X, Y, means, stds) or None if insufficient data
        """
        if len(series) < window + horizon:
            return None

        sensor_data, timestamps = self.series_to_array(series)
        sensor_data = self.fill_gaps(sensor_data)
        sensor_norm, means, stds = self.normalize(sensor_data)
        temporal = self.add_temporal(timestamps)
        full_data = np.concatenate([sensor_norm, temporal], axis=1)

        X, Y = self.create_windows(full_data, window, horizon)
        if X.shape[0] == 0:
            return None

        return X, Y, means, stds
