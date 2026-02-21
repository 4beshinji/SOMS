"""Unit tests for tracking.reid_embedder — ReID feature extraction."""
import sys
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

from conftest import make_embedding

# conftest.py pre-installs mocks for cv2, torch, torchvision, torchreid
# so we can import the module without the real heavy packages.
from tracking.reid_embedder import ReIDEmbedder
from tracking import reid_embedder as _reid_module


# ── Helpers ──────────────────────────────────────────────────────


def _get_mocks():
    """Retrieve the mock modules installed by conftest."""
    return {
        "cv2": sys.modules["cv2"],
        "torch": sys.modules["torch"],
        # F is resolved as torch.nn.functional (attribute), NOT sys.modules entry
        "F": _reid_module.F,
        "torchreid": sys.modules["torchreid"],
    }


def _make_embedder():
    """Create a fresh ReIDEmbedder with mocked torchreid model.

    Returns (embedder, mock_model) so tests can configure model behavior.
    """
    ReIDEmbedder._instance = None

    mock_torchreid = sys.modules["torchreid"]
    mock_model = MagicMock()
    mock_model.eval.return_value = None
    mock_model.to.return_value = mock_model
    mock_torchreid.models.build_model.return_value = mock_model

    embedder = ReIDEmbedder("osnet_x0_5")

    return embedder, mock_model


# ── Tests: compute_similarity (pure numpy, no mocking needed) ────


class TestComputeSimilarity:
    """Tests for the static compute_similarity method.

    This only uses numpy.dot, so we test the math directly.
    """

    def test_identical_embeddings(self):
        """Identical L2-normalized vectors have cosine similarity 1.0."""
        emb = make_embedding(seed=42)
        sim = ReIDEmbedder.compute_similarity(emb, emb)
        assert sim == pytest.approx(1.0, abs=1e-5)

    def test_orthogonal_embeddings(self):
        """Orthogonal vectors have cosine similarity 0.0."""
        a = np.zeros(512, dtype=np.float32)
        a[0] = 1.0
        b = np.zeros(512, dtype=np.float32)
        b[1] = 1.0

        sim = ReIDEmbedder.compute_similarity(a, b)
        assert sim == pytest.approx(0.0, abs=1e-7)

    def test_opposite_embeddings(self):
        """Opposite vectors have cosine similarity -1.0."""
        emb = make_embedding(seed=7)
        opposite = -emb

        sim = ReIDEmbedder.compute_similarity(emb, opposite)
        assert sim == pytest.approx(-1.0, abs=1e-5)

    def test_similar_embeddings_high_score(self):
        """Slightly perturbed embeddings still have high similarity."""
        emb = make_embedding(seed=10)
        noise = np.random.RandomState(99).randn(512).astype(np.float32) * 0.001
        perturbed = emb + noise
        perturbed /= np.linalg.norm(perturbed)

        sim = ReIDEmbedder.compute_similarity(emb, perturbed)
        assert sim > 0.99

    def test_different_embeddings_low_score(self):
        """Completely different random embeddings have low similarity."""
        a = make_embedding(seed=1)
        b = make_embedding(seed=9999)

        sim = ReIDEmbedder.compute_similarity(a, b)
        # Random 512-dim vectors should have near-zero cosine similarity
        assert abs(sim) < 0.2


# ── Tests: ReIDEmbedder initialization ───────────────────────────


class TestReIDEmbedderInit:
    """Tests for ReIDEmbedder initialization and singleton pattern."""

    def setup_method(self):
        ReIDEmbedder._instance = None

    def test_singleton_pattern(self):
        """get_instance returns the same object on repeated calls."""
        embedder1, _ = _make_embedder()
        # Manually assign to class singleton
        ReIDEmbedder._instance = embedder1

        inst2 = ReIDEmbedder.get_instance("osnet_x0_5")
        assert embedder1 is inst2

        ReIDEmbedder._instance = None

    def test_model_set_to_eval_mode(self):
        """Model is set to eval mode during initialization."""
        embedder, mock_model = _make_embedder()
        mock_model.eval.assert_called_once()

        ReIDEmbedder._instance = None

    def test_uses_cpu_when_no_gpu(self):
        """Selects CPU device when CUDA is unavailable."""
        mock_torch = sys.modules["torch"]
        mock_torch.cuda.is_available.return_value = False
        mock_torch.device.side_effect = lambda name: name

        embedder, _ = _make_embedder()
        mock_torch.device.assert_called_with("cpu")

        ReIDEmbedder._instance = None

    def test_builds_model_with_correct_args(self):
        """torchreid.models.build_model is called with correct arguments."""
        mock_torchreid = sys.modules["torchreid"]
        embedder, _ = _make_embedder()

        mock_torchreid.models.build_model.assert_called_with(
            name="osnet_x0_5",
            num_classes=1,
            pretrained=True,
        )

        ReIDEmbedder._instance = None


# ── Tests: ReIDEmbedder.extract() ────────────────────────────────


class TestReIDEmbedderExtract:
    """Tests for the extract() method."""

    def setup_method(self):
        ReIDEmbedder._instance = None

    def test_extract_empty_bboxes_returns_empty_list(self):
        """extract() returns empty list for empty bboxes."""
        embedder, _ = _make_embedder()
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        result = embedder.extract(image, [])
        assert result == []

        ReIDEmbedder._instance = None

    def test_extract_calls_model_inference(self):
        """extract() runs the model in no_grad mode and normalizes output."""
        embedder, mock_model = _make_embedder()
        mock_torch = sys.modules["torch"]
        mock_cv2 = sys.modules["cv2"]

        # Configure cv2 mocks
        mock_cv2.resize.return_value = np.zeros((256, 128, 3), dtype=np.uint8)
        mock_cv2.cvtColor.return_value = np.zeros((256, 128, 3), dtype=np.uint8)

        # torch.stack returns a tensor that can be moved to device
        mock_batch = MagicMock()
        mock_batch_on_device = MagicMock()
        mock_batch.to.return_value = mock_batch_on_device
        mock_torch.stack.return_value = mock_batch

        # torch.no_grad() context manager
        mock_no_grad = MagicMock()
        mock_no_grad.__enter__ = MagicMock(return_value=None)
        mock_no_grad.__exit__ = MagicMock(return_value=False)
        mock_torch.no_grad.return_value = mock_no_grad

        # Model returns raw features; F.normalize returns list of tensors
        emb_tensor = MagicMock()
        emb_tensor.cpu.return_value.numpy.return_value = make_embedding(seed=42)
        # F.normalize is called on model output; mock it to return our tensor list
        raw_features = MagicMock()
        raw_features.__iter__ = MagicMock(return_value=iter([emb_tensor]))
        mock_model.return_value = raw_features
        # The actual F module is torch.nn.functional
        mock_F = _reid_module.F
        mock_F.normalize.return_value = [emb_tensor]

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        bboxes = [[100.0, 100.0, 200.0, 300.0]]

        result = embedder.extract(image, bboxes)

        # Model was called
        assert mock_model.called
        assert len(result) == 1

        ReIDEmbedder._instance = None

    def test_extract_invalid_bbox_uses_blank_crop(self):
        """extract() uses a blank crop for bboxes where x2 <= x1."""
        embedder, mock_model = _make_embedder()
        mock_torch = sys.modules["torch"]
        mock_F = _reid_module.F
        mock_cv2 = sys.modules["cv2"]

        mock_cv2.resize.reset_mock()
        mock_cv2.cvtColor.return_value = np.zeros((256, 128, 3), dtype=np.uint8)

        mock_batch = MagicMock()
        mock_batch.to.return_value = MagicMock()
        mock_torch.stack.return_value = mock_batch

        mock_no_grad = MagicMock()
        mock_no_grad.__enter__ = MagicMock(return_value=None)
        mock_no_grad.__exit__ = MagicMock(return_value=False)
        mock_torch.no_grad.return_value = mock_no_grad

        emb_tensor = MagicMock()
        emb_tensor.cpu.return_value.numpy.return_value = make_embedding(seed=1)
        mock_model.return_value = MagicMock()
        mock_F.normalize.return_value = [emb_tensor]

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        bboxes = [[200.0, 100.0, 100.0, 300.0]]

        result = embedder.extract(image, bboxes)

        mock_cv2.resize.assert_not_called()
        assert len(result) == 1

        ReIDEmbedder._instance = None

    def test_extract_clamps_bbox_to_image_bounds(self):
        """extract() clamps bounding box coordinates to image dimensions."""
        embedder, mock_model = _make_embedder()
        mock_torch = sys.modules["torch"]
        mock_F = _reid_module.F
        mock_cv2 = sys.modules["cv2"]

        mock_cv2.resize.return_value = np.zeros((256, 128, 3), dtype=np.uint8)
        mock_cv2.cvtColor.return_value = np.zeros((256, 128, 3), dtype=np.uint8)

        mock_batch = MagicMock()
        mock_batch.to.return_value = MagicMock()
        mock_torch.stack.return_value = mock_batch

        mock_no_grad = MagicMock()
        mock_no_grad.__enter__ = MagicMock(return_value=None)
        mock_no_grad.__exit__ = MagicMock(return_value=False)
        mock_torch.no_grad.return_value = mock_no_grad

        emb_tensor = MagicMock()
        emb_tensor.cpu.return_value.numpy.return_value = make_embedding(seed=1)
        mock_model.return_value = MagicMock()
        mock_F.normalize.return_value = [emb_tensor]

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        bboxes = [[-50.0, -50.0, 800.0, 600.0]]

        result = embedder.extract(image, bboxes)
        assert len(result) == 1

        ReIDEmbedder._instance = None

    def test_extract_multiple_bboxes(self):
        """extract() processes multiple bounding boxes in a batch."""
        embedder, mock_model = _make_embedder()
        mock_torch = sys.modules["torch"]
        mock_F = _reid_module.F
        mock_cv2 = sys.modules["cv2"]

        mock_cv2.resize.return_value = np.zeros((256, 128, 3), dtype=np.uint8)
        mock_cv2.cvtColor.return_value = np.zeros((256, 128, 3), dtype=np.uint8)

        mock_batch = MagicMock()
        mock_batch.to.return_value = MagicMock()
        mock_torch.stack.return_value = mock_batch

        mock_no_grad = MagicMock()
        mock_no_grad.__enter__ = MagicMock(return_value=None)
        mock_no_grad.__exit__ = MagicMock(return_value=False)
        mock_torch.no_grad.return_value = mock_no_grad

        emb1 = MagicMock()
        emb1.cpu.return_value.numpy.return_value = make_embedding(seed=1)
        emb2 = MagicMock()
        emb2.cpu.return_value.numpy.return_value = make_embedding(seed=2)
        emb3 = MagicMock()
        emb3.cpu.return_value.numpy.return_value = make_embedding(seed=3)

        mock_model.return_value = MagicMock()
        mock_F.normalize.return_value = [emb1, emb2, emb3]

        image = np.zeros((480, 640, 3), dtype=np.uint8)
        bboxes = [
            [10.0, 10.0, 100.0, 200.0],
            [200.0, 50.0, 300.0, 250.0],
            [400.0, 100.0, 500.0, 300.0],
        ]

        result = embedder.extract(image, bboxes)

        assert len(result) == 3
        for emb in result:
            assert isinstance(emb, np.ndarray)
            assert emb.shape == (512,)

        ReIDEmbedder._instance = None
