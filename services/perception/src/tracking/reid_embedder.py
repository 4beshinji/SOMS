"""
ReID (Re-Identification) feature extractor using OSNet x0.5.

Extracts L2-normalized 512-dim appearance embeddings from person crops.
Singleton pattern for GPU memory efficiency.
"""
from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from torchvision import transforms

logger = logging.getLogger(__name__)

# Image preprocessing for OSNet (ImageNet normalization)
_TRANSFORM = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# OSNet input size
_INPUT_HEIGHT = 256
_INPUT_WIDTH = 128


class ReIDEmbedder:
    _instance: Optional[ReIDEmbedder] = None

    @classmethod
    def get_instance(cls, model_name: str = "osnet_x0_5") -> ReIDEmbedder:
        if cls._instance is None:
            cls._instance = cls(model_name)
        return cls._instance

    def __init__(self, model_name: str = "osnet_x0_5"):
        logger.info("Loading ReID model: %s", model_name)

        import torchreid

        self._model = torchreid.models.build_model(
            name=model_name,
            num_classes=1,  # feature extraction only
            pretrained=True,
        )
        self._model.eval()

        # Use GPU if available
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model = self._model.to(self._device)

        logger.info("ReID model loaded on %s", self._device)

    def extract(
        self, image: np.ndarray, bboxes: list[list[float]]
    ) -> list[np.ndarray]:
        """
        Extract ReID embeddings for detected persons.

        Args:
            image: Full BGR frame.
            bboxes: List of [x1, y1, x2, y2] bounding boxes.

        Returns:
            List of L2-normalized 512-dim numpy arrays.
        """
        if not bboxes:
            return []

        h, w = image.shape[:2]
        crops = []

        for bbox in bboxes:
            x1 = max(0, int(bbox[0]))
            y1 = max(0, int(bbox[1]))
            x2 = min(w, int(bbox[2]))
            y2 = min(h, int(bbox[3]))

            if x2 <= x1 or y2 <= y1:
                # Invalid bbox — use a blank crop
                crop = np.zeros((_INPUT_HEIGHT, _INPUT_WIDTH, 3), dtype=np.uint8)
            else:
                crop = image[y1:y2, x1:x2]
                crop = cv2.resize(crop, (_INPUT_WIDTH, _INPUT_HEIGHT))

            # BGR -> RGB
            crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            crops.append(_TRANSFORM(crop))

        batch = torch.stack(crops).to(self._device)

        with torch.no_grad():
            features = self._model(batch)
            # L2 normalize
            features = F.normalize(features, p=2, dim=1)

        return [f.cpu().numpy() for f in features]

    @staticmethod
    def compute_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two L2-normalized embeddings."""
        return float(np.dot(a, b))
