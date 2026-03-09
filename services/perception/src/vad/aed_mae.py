"""AED-MAE: Self-Distilled Masked Auto-Encoder for frame-level anomaly detection.

Reconstructs masked patches of input frames. High reconstruction error
indicates scene anomaly (unusual objects, lighting, spatial layout).

Architecture:
    Input: (C, H, W) frame → patchify → mask 75% → encoder → decoder → reconstruct
    Score: MSE between original and reconstructed patches

Reference: Ristea et al., "Self-Distilled Masked Auto-Encoders are
Efficient Video Anomaly Detectors" (CVPR 2024)
"""
from __future__ import annotations

import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# Default input size for the MAE
INPUT_H, INPUT_W = 64, 64
PATCH_SIZE = 8
N_PATCHES = (INPUT_H // PATCH_SIZE) * (INPUT_W // PATCH_SIZE)  # 64


if TORCH_AVAILABLE:

    class PatchEmbed(nn.Module):
        """Convert image to patch embeddings."""

        def __init__(
            self,
            img_size: int = 64,
            patch_size: int = 8,
            in_channels: int = 3,
            embed_dim: int = 128,
        ):
            super().__init__()
            self.n_patches = (img_size // patch_size) ** 2
            self.proj = nn.Conv2d(
                in_channels, embed_dim, kernel_size=patch_size, stride=patch_size
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """(B, C, H, W) → (B, n_patches, embed_dim)"""
            return self.proj(x).flatten(2).transpose(1, 2)

    class MAEEncoder(nn.Module):
        """Lightweight Transformer encoder operating on visible patches only."""

        def __init__(
            self,
            n_patches: int = 64,
            embed_dim: int = 128,
            depth: int = 2,
            nhead: int = 4,
        ):
            super().__init__()
            self.pos_embed = nn.Parameter(torch.randn(1, n_patches, embed_dim) * 0.02)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=embed_dim,
                nhead=nhead,
                dim_feedforward=embed_dim * 4,
                batch_first=True,
                dropout=0.0,
            )
            self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=depth)
            self.norm = nn.LayerNorm(embed_dim)

        def forward(
            self, x: torch.Tensor, visible_idx: torch.Tensor
        ) -> torch.Tensor:
            """Encode only visible patches.

            Args:
                x: (B, n_visible, embed_dim) visible patch embeddings
                visible_idx: (B, n_visible) indices for positional encoding

            Returns:
                (B, n_visible, embed_dim) encoded features
            """
            # Gather positional embeddings for visible patches
            pos = self.pos_embed.expand(x.shape[0], -1, -1)
            pos_visible = torch.gather(
                pos, 1, visible_idx.unsqueeze(-1).expand(-1, -1, x.shape[-1])
            )
            h = x + pos_visible
            h = self.transformer(h)
            return self.norm(h)

    class MAEDecoder(nn.Module):
        """Lightweight decoder that reconstructs all patches from visible ones."""

        def __init__(
            self,
            n_patches: int = 64,
            embed_dim: int = 128,
            decoder_dim: int = 64,
            depth: int = 1,
            nhead: int = 4,
            patch_dim: int = 192,  # patch_size^2 * 3
        ):
            super().__init__()
            self.mask_token = nn.Parameter(torch.randn(1, 1, decoder_dim) * 0.02)
            self.enc_to_dec = nn.Linear(embed_dim, decoder_dim)
            self.pos_embed = nn.Parameter(torch.randn(1, n_patches, decoder_dim) * 0.02)

            encoder_layer = nn.TransformerEncoderLayer(
                d_model=decoder_dim,
                nhead=nhead,
                dim_feedforward=decoder_dim * 4,
                batch_first=True,
                dropout=0.0,
            )
            self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=depth)
            self.pred = nn.Linear(decoder_dim, patch_dim)

        def forward(
            self,
            encoded: torch.Tensor,
            visible_idx: torch.Tensor,
            masked_idx: torch.Tensor,
            n_patches: int,
        ) -> torch.Tensor:
            """Reconstruct masked patches.

            Returns:
                (B, n_masked, patch_dim) reconstructed patch pixels
            """
            B = encoded.shape[0]
            h = self.enc_to_dec(encoded)

            # Create full sequence with mask tokens
            mask_tokens = self.mask_token.expand(B, masked_idx.shape[1], -1)
            full = torch.zeros(B, n_patches, h.shape[-1], device=h.device)
            full.scatter_(
                1, visible_idx.unsqueeze(-1).expand(-1, -1, h.shape[-1]), h
            )
            full.scatter_(
                1, masked_idx.unsqueeze(-1).expand(-1, -1, h.shape[-1]), mask_tokens
            )

            full = full + self.pos_embed[:, :n_patches]
            full = self.transformer(full)

            # Extract masked positions
            masked_output = torch.gather(
                full, 1, masked_idx.unsqueeze(-1).expand(-1, -1, full.shape[-1])
            )
            return self.pred(masked_output)

    class AED_MAE(nn.Module):
        """Complete Masked Auto-Encoder for anomaly detection.

        ~150K params — runs at >1000 FPS on GPU, >100 FPS on CPU.
        """

        def __init__(
            self,
            img_size: int = 64,
            patch_size: int = 8,
            in_channels: int = 3,
            embed_dim: int = 128,
            decoder_dim: int = 64,
            encoder_depth: int = 2,
            decoder_depth: int = 1,
            nhead: int = 4,
            mask_ratio: float = 0.75,
        ):
            super().__init__()
            self.patch_size = patch_size
            self.mask_ratio = mask_ratio
            self.n_patches = (img_size // patch_size) ** 2
            self.patch_dim = patch_size * patch_size * in_channels

            self.patch_embed = PatchEmbed(img_size, patch_size, in_channels, embed_dim)
            self.encoder = MAEEncoder(self.n_patches, embed_dim, encoder_depth, nhead)
            self.decoder = MAEDecoder(
                self.n_patches, embed_dim, decoder_dim, decoder_depth, nhead, self.patch_dim
            )

        def _random_mask(
            self, B: int, device: torch.device
        ) -> tuple[torch.Tensor, torch.Tensor]:
            """Generate random mask indices."""
            n_visible = int(self.n_patches * (1 - self.mask_ratio))
            noise = torch.rand(B, self.n_patches, device=device)
            ids_sorted = torch.argsort(noise, dim=1)
            visible = ids_sorted[:, :n_visible]
            masked = ids_sorted[:, n_visible:]
            return visible, masked

        def _patchify(self, img: torch.Tensor) -> torch.Tensor:
            """(B, C, H, W) → (B, n_patches, patch_dim)"""
            p = self.patch_size
            B, C, H, W = img.shape
            patches = img.reshape(B, C, H // p, p, W // p, p)
            patches = patches.permute(0, 2, 4, 1, 3, 5).reshape(B, -1, self.patch_dim)
            return patches

        def forward(
            self, img: torch.Tensor, mask: tuple | None = None
        ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
            """Forward pass.

            Returns:
                (reconstructed, target, masked_idx)
            """
            B = img.shape[0]
            patches = self.patch_embed(img)
            target = self._patchify(img)

            if mask is None:
                visible_idx, masked_idx = self._random_mask(B, img.device)
            else:
                visible_idx, masked_idx = mask

            # Select visible patches
            visible_patches = torch.gather(
                patches, 1, visible_idx.unsqueeze(-1).expand(-1, -1, patches.shape[-1])
            )
            encoded = self.encoder(visible_patches, visible_idx)
            reconstructed = self.decoder(encoded, visible_idx, masked_idx, self.n_patches)

            # Target for masked patches only
            masked_target = torch.gather(
                target, 1, masked_idx.unsqueeze(-1).expand(-1, -1, self.patch_dim)
            )
            return reconstructed, masked_target, masked_idx

        def anomaly_score(self, img: torch.Tensor, n_augments: int = 4) -> torch.Tensor:
            """Compute anomaly score by averaging over multiple random masks.

            Args:
                img: (B, C, H, W) input frames
                n_augments: number of random masks to average over

            Returns:
                (B,) anomaly scores (MSE, higher = more anomalous)
            """
            scores = []
            for _ in range(n_augments):
                recon, target, _ = self.forward(img)
                mse = F.mse_loss(recon, target, reduction="none").mean(dim=(1, 2))
                scores.append(mse)
            return torch.stack(scores).mean(dim=0)


class AEDMAEDetector:
    """Wrapper that preprocesses frames and runs AED-MAE inference."""

    def __init__(
        self,
        model_path: str | None = None,
        device: str = "cpu",
        img_size: int = 64,
        n_augments: int = 4,
    ):
        self._device = device
        self._img_size = img_size
        self._n_augments = n_augments
        self._model: AED_MAE | None = None
        self._running_stats = {"mean": 0.0, "var": 1.0, "count": 0}

        if TORCH_AVAILABLE:
            try:
                self._model = AED_MAE(img_size=img_size)
                if model_path and os.path.exists(model_path):
                    checkpoint = torch.load(model_path, map_location=device, weights_only=True)
                    self._model.load_state_dict(checkpoint["model_state_dict"])
                    stats = checkpoint.get("running_stats")
                    if stats:
                        self._running_stats = stats
                    logger.info("Loaded AED-MAE model from %s", model_path)
                self._model.to(device)
                self._model.eval()
            except Exception:
                self._model = None

    def score_frame(self, frame: np.ndarray) -> float | None:
        """Compute anomaly score for a single frame.

        Args:
            frame: (H, W, 3) BGR image (any size, will be resized)

        Returns:
            Z-scored anomaly score or None
        """
        if not TORCH_AVAILABLE or self._model is None:
            return None

        # Preprocess: resize, normalize to [0, 1], CHW
        import cv2

        resized = cv2.resize(frame, (self._img_size, self._img_size))
        tensor = torch.FloatTensor(resized).permute(2, 0, 1).unsqueeze(0) / 255.0
        tensor = tensor.to(self._device)

        with torch.no_grad():
            raw_score = self._model.anomaly_score(tensor, self._n_augments)
        raw = float(raw_score.item())

        # Update running statistics for Z-scoring
        self._update_stats(raw)

        # Z-score
        std = max(self._running_stats["var"] ** 0.5, 1e-6)
        return (raw - self._running_stats["mean"]) / std

    def _update_stats(self, value: float):
        """Welford's online algorithm for running mean/variance."""
        n = self._running_stats["count"] + 1
        old_mean = self._running_stats["mean"]
        new_mean = old_mean + (value - old_mean) / n
        new_var = (
            self._running_stats["var"] * (n - 1) + (value - old_mean) * (value - new_mean)
        ) / max(n, 1)
        self._running_stats = {"mean": new_mean, "var": new_var, "count": n}
