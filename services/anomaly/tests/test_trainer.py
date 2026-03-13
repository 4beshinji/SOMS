"""Tests for the model trainer (mocked ML deps)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

from data.preprocessor import Preprocessor


class TestTrainerLogic:
    def test_preprocessor_integration(self):
        """Verify preprocessor produces correct shapes for trainer."""
        pp = Preprocessor()
        series = []
        for i in range(200):
            from datetime import datetime, timezone
            entry = {"timestamp": datetime(2026, 1, 1 + i // 24, i % 24, tzinfo=timezone.utc)}
            for ch in Preprocessor.CHANNELS:
                entry[f"avg_{ch}"] = 20.0 + np.random.randn()
                entry[f"max_{ch}"] = 25.0 + np.random.randn()
                entry[f"min_{ch}"] = 15.0 + np.random.randn()
            series.append(entry)

        result = pp.prepare_training_data(series, window=168, horizon=6)
        assert result is not None
        X, Y, means, stds = result
        assert X.shape[2] == 22  # 18 sensor + 4 temporal
        assert Y.shape[2] == 6   # 6 channel avg targets
        assert means.shape == (18,)
        assert stds.shape == (18,)

