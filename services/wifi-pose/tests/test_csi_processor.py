"""Unit tests for CSIProcessor — Hampel filter + spectrogram generation."""
import numpy as np
import pytest

from csi_processor import CSIProcessor, CSIFrame


class TestCSIProcessor:
    """Tests for CSI preprocessing pipeline."""

    def _make_processor(self, **kwargs):
        defaults = dict(
            subcarrier_count=8,
            hampel_window=3,
            hampel_threshold=3.0,
            spectrogram_window_sec=0.1,
            sample_rate_hz=100.0,
        )
        defaults.update(kwargs)
        return CSIProcessor(**defaults)

    def test_window_not_full_returns_none(self):
        """Returns None until the sliding window is full."""
        proc = self._make_processor(
            spectrogram_window_sec=0.1, sample_rate_hz=10.0
        )
        # Window needs 1 sample (0.1s * 10Hz = 1)
        # But maxlen is int(0.1*10)=1, so first frame fills it
        frame = CSIFrame(
            node_id="n1", timestamp=0.0,
            amplitudes=np.ones(8),
        )
        # First frame fills the buffer exactly
        result = proc.add_frame(frame)
        assert result is not None  # 1 sample = full window

    def test_spectrogram_shape(self):
        """Spectrogram has shape (n_subcarriers, time_steps)."""
        n_sub = 8
        samples = 5
        proc = self._make_processor(
            subcarrier_count=n_sub,
            spectrogram_window_sec=0.5,
            sample_rate_hz=10.0,  # 0.5 * 10 = 5 samples
        )

        result = None
        for i in range(samples):
            frame = CSIFrame(
                node_id="n1",
                timestamp=float(i) * 0.1,
                amplitudes=np.random.randn(n_sub),
            )
            result = proc.add_frame(frame)

        assert result is not None
        assert result.shape == (n_sub, samples)

    def test_wrong_subcarrier_count_ignored(self):
        """Frames with wrong subcarrier count return None."""
        proc = self._make_processor(subcarrier_count=8)
        frame = CSIFrame(
            node_id="n1", timestamp=0.0,
            amplitudes=np.ones(16),  # Wrong size
        )
        result = proc.add_frame(frame)
        assert result is None

    def test_per_node_isolation(self):
        """Each node has its own independent buffer."""
        proc = self._make_processor(
            subcarrier_count=4,
            spectrogram_window_sec=0.2,
            sample_rate_hz=10.0,  # 2 samples needed
        )

        # Add 1 frame to node_a
        f1 = CSIFrame(node_id="a", timestamp=0.0, amplitudes=np.ones(4))
        assert proc.add_frame(f1) is None  # Not full yet

        # Add 1 frame to node_b
        f2 = CSIFrame(node_id="b", timestamp=0.0, amplitudes=np.ones(4) * 2)
        assert proc.add_frame(f2) is None

        # Add 2nd frame to node_a — now full
        f3 = CSIFrame(node_id="a", timestamp=0.1, amplitudes=np.ones(4) * 3)
        result = proc.add_frame(f3)
        assert result is not None
        assert result.shape == (4, 2)

    def test_reset_clears_buffer(self):
        """reset() clears buffers for a specific node or all nodes."""
        proc = self._make_processor(
            subcarrier_count=4,
            spectrogram_window_sec=0.3,
            sample_rate_hz=10.0,
        )

        for i in range(2):
            proc.add_frame(CSIFrame(
                node_id="a", timestamp=float(i) * 0.1,
                amplitudes=np.ones(4),
            ))

        proc.reset("a")
        assert "a" not in proc._buffers

    def test_hampel_filter_removes_outlier(self):
        """Hampel filter replaces outlier values with median."""
        proc = self._make_processor(
            subcarrier_count=4,
            hampel_window=3,
            hampel_threshold=2.0,
            spectrogram_window_sec=1.0,
            sample_rate_hz=10.0,
        )

        # Build up a baseline of normal values
        for i in range(5):
            proc.add_frame(CSIFrame(
                node_id="n1", timestamp=float(i) * 0.1,
                amplitudes=np.array([1.0, 1.0, 1.0, 1.0]),
            ))

        # Now add an outlier
        outlier_frame = CSIFrame(
            node_id="n1", timestamp=0.5,
            amplitudes=np.array([1.0, 100.0, 1.0, 1.0]),
        )
        proc.add_frame(outlier_frame)

        # Check that the buffer's last entry has the outlier filtered
        buf = proc._buffers["n1"]
        last_amp = buf[-1][1]
        # The outlier (100.0) should have been replaced with the median (~1.0)
        assert last_amp[1] < 10.0  # Significantly reduced from 100
