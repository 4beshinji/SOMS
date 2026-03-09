"""Tests for the data preprocessor."""
import math
from datetime import datetime, timezone

import numpy as np
import pytest

# Import with src on path (conftest adds it)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from data.preprocessor import Preprocessor


@pytest.fixture
def preprocessor():
    return Preprocessor()


class TestSeriesConversion:
    def test_empty_series(self, preprocessor):
        data, ts = preprocessor.series_to_array([])
        assert data.shape == (0, 18)
        assert ts == []

    def test_single_entry(self, preprocessor):
        series = [{"timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc), "avg_temperature": 22.5}]
        data, ts = preprocessor.series_to_array(series)
        assert data.shape == (1, 18)
        assert data[0, 0] == 22.5  # avg_temperature is index 0
        assert len(ts) == 1

    def test_all_channels(self, preprocessor):
        entry = {"timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc)}
        for ch in Preprocessor.CHANNELS:
            for stat in Preprocessor.STATS:
                entry[f"{stat}_{ch}"] = 1.0
        data, _ = preprocessor.series_to_array([entry])
        assert not np.any(np.isnan(data))

    def test_missing_channels_are_nan(self, preprocessor):
        series = [{"timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc)}]
        data, _ = preprocessor.series_to_array(series)
        assert np.all(np.isnan(data))


class TestFillGaps:
    def test_no_gaps(self):
        data = np.array([[1.0, 2.0], [3.0, 4.0]])
        result = Preprocessor.fill_gaps(data)
        np.testing.assert_array_equal(result, data)

    def test_interpolation(self):
        data = np.array([[1.0], [np.nan], [3.0]])
        result = Preprocessor.fill_gaps(data)
        assert result[1, 0] == pytest.approx(2.0)

    def test_all_nan_fills_zero(self):
        data = np.array([[np.nan], [np.nan]])
        result = Preprocessor.fill_gaps(data)
        np.testing.assert_array_equal(result, [[0.0], [0.0]])

    def test_edge_nans(self):
        data = np.array([[np.nan], [2.0], [np.nan]])
        result = Preprocessor.fill_gaps(data)
        # np.interp extrapolates with edge values
        assert result[0, 0] == pytest.approx(2.0)
        assert result[2, 0] == pytest.approx(2.0)


class TestTemporalEncoding:
    def test_midnight(self):
        ts = [datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)]  # Monday
        result = Preprocessor.add_temporal(ts)
        assert result.shape == (1, 4)
        assert result[0, 0] == pytest.approx(math.sin(0), abs=1e-6)  # hour_sin at 0
        assert result[0, 1] == pytest.approx(math.cos(0), abs=1e-6)  # hour_cos at 0

    def test_noon(self):
        ts = [datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)]
        result = Preprocessor.add_temporal(ts)
        assert result[0, 0] == pytest.approx(math.sin(2 * math.pi * 12 / 24), abs=1e-6)

    def test_weekend_encoding(self):
        # Sunday = weekday 6
        ts = [datetime(2026, 1, 4, 0, 0, tzinfo=timezone.utc)]  # Sunday
        result = Preprocessor.add_temporal(ts)
        assert result[0, 2] == pytest.approx(math.sin(2 * math.pi * 6 / 7), abs=1e-6)


class TestNormalize:
    def test_basic(self):
        data = np.array([[1.0, 10.0], [3.0, 20.0], [5.0, 30.0]])
        norm, means, stds = Preprocessor.normalize(data)
        assert means[0] == pytest.approx(3.0)
        assert means[1] == pytest.approx(20.0)
        assert norm[1, 0] == pytest.approx(0.0, abs=1e-6)  # mean → 0

    def test_with_provided_stats(self):
        data = np.array([[10.0]])
        norm, _, _ = Preprocessor.normalize(data, means=np.array([5.0]), stds=np.array([2.5]))
        assert norm[0, 0] == pytest.approx(2.0)

    def test_zero_std_safe(self):
        data = np.array([[5.0], [5.0], [5.0]])
        norm, _, stds = Preprocessor.normalize(data)
        assert not np.any(np.isinf(norm))


class TestCreateWindows:
    def test_basic(self):
        data = np.random.randn(180, 22)
        X, Y = Preprocessor.create_windows(data, window=168, horizon=6)
        assert X.shape == (7, 168, 22)
        assert Y.shape == (7, 6, 6)

    def test_insufficient_data(self):
        data = np.random.randn(100, 22)
        X, Y = Preprocessor.create_windows(data, window=168, horizon=6)
        assert X.shape[0] == 0

    def test_target_is_avg_values(self):
        data = np.zeros((180, 22))
        # Set avg_temperature (index 0) to known pattern
        for i in range(180):
            data[i, 0] = float(i)
        X, Y = Preprocessor.create_windows(data, window=168, horizon=6)
        # First sample target should be data[168:174, 0]
        np.testing.assert_array_equal(Y[0, :, 0], np.arange(168, 174, dtype=float))


class TestRawToHourly:
    def test_single_channel(self, preprocessor):
        now = datetime.now(timezone.utc)
        buf = {"temperature": [(now, 22.0), (now, 24.0), (now, 20.0)]}
        result = preprocessor.raw_to_hourly_features(buf)
        assert result.shape == (1, 18)
        assert result[0, 0] == pytest.approx(22.0)  # avg
        assert result[0, 1] == pytest.approx(24.0)  # max
        assert result[0, 2] == pytest.approx(20.0)  # min

    def test_empty_buffer(self, preprocessor):
        result = preprocessor.raw_to_hourly_features({})
        assert result.shape == (1, 18)
        assert np.all(np.isnan(result))


class TestPrepareTraining:
    def test_insufficient_data(self, preprocessor):
        series = [{"timestamp": datetime(2026, 1, 1, i, tzinfo=timezone.utc)} for i in range(10)]
        result = preprocessor.prepare_training_data(series, window=168, horizon=6)
        assert result is None

    def test_sufficient_data(self, preprocessor):
        series = []
        for i in range(200):
            entry = {"timestamp": datetime(2026, 1, 1 + i // 24, i % 24, tzinfo=timezone.utc)}
            for ch in Preprocessor.CHANNELS:
                entry[f"avg_{ch}"] = 20.0 + np.random.randn()
                entry[f"max_{ch}"] = 25.0 + np.random.randn()
                entry[f"min_{ch}"] = 15.0 + np.random.randn()
            series.append(entry)
        result = preprocessor.prepare_training_data(series, window=168, horizon=6)
        assert result is not None
        X, Y, means, stds = result
        assert X.shape[1] == 168
        assert X.shape[2] == 22
        assert Y.shape[1] == 6
        assert Y.shape[2] == 6
