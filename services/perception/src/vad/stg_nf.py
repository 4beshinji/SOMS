"""STG-NF: Spatio-Temporal Graph Normalizing Flow for pose-based anomaly detection.

Consumes YOLO-pose skeleton sequences (17 COCO keypoints) and scores
each frame by the negative log-likelihood under a normalizing flow
trained on normal-only pose sequences.

Architecture:
    Input: (T, 17, 2) skeleton sequence → graph convolution → normalizing flow
    Output: anomaly score per frame (higher = more anomalous)

Reference: Hirschorn & Avidan, "Normalizing Flows for Human Pose Anomaly
Detection" (ICCV 2023)
"""
from __future__ import annotations

import logging
import os
from collections import deque
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# COCO skeleton adjacency (17 joints, undirected edges)
COCO_EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 4),          # head
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),  # arms
    (5, 11), (6, 12), (11, 12),                # torso
    (11, 13), (13, 15), (12, 14), (14, 16),    # legs
]


@dataclass
class PoseFrame:
    timestamp: float
    keypoints: np.ndarray      # (N_persons, 17, 2)
    confidences: np.ndarray    # (N_persons, 17)


def _build_adjacency(n_joints: int = 17) -> np.ndarray:
    """Build symmetric adjacency matrix from COCO skeleton."""
    A = np.eye(n_joints, dtype=np.float32)
    for i, j in COCO_EDGES:
        A[i, j] = 1.0
        A[j, i] = 1.0
    # Degree normalization: D^{-1/2} A D^{-1/2}
    D = np.sum(A, axis=1)
    D_inv_sqrt = np.diag(1.0 / np.sqrt(np.maximum(D, 1e-6)))
    return D_inv_sqrt @ A @ D_inv_sqrt


if TORCH_AVAILABLE:

    class GraphConvLayer(nn.Module):
        """Single-layer graph convolution: X' = σ(A_norm · X · W)"""

        def __init__(self, in_features: int, out_features: int, n_joints: int = 17):
            super().__init__()
            self.W = nn.Linear(in_features, out_features, bias=True)
            A_norm = _build_adjacency(n_joints)
            self.register_buffer("A", torch.from_numpy(A_norm))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """x: (batch, n_joints, in_features) → (batch, n_joints, out_features)"""
            # Graph conv: A · X
            h = torch.matmul(self.A.unsqueeze(0), x)
            return torch.relu(self.W(h))

    class CouplingLayer(nn.Module):
        """Affine coupling layer for normalizing flow."""

        def __init__(self, dim: int, hidden: int = 64):
            super().__init__()
            half = dim // 2
            self.net = nn.Sequential(
                nn.Linear(half, hidden),
                nn.ReLU(),
                nn.Linear(hidden, hidden),
                nn.ReLU(),
                nn.Linear(hidden, (dim - half) * 2),
            )
            self.half = half

        def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            """Forward: x → z, returns (z, log_det_J)"""
            x1, x2 = x[:, : self.half], x[:, self.half :]
            params = self.net(x1)
            log_s, t = params.chunk(2, dim=-1)
            log_s = torch.tanh(log_s) * 2  # stabilize
            z2 = x2 * torch.exp(log_s) + t
            z = torch.cat([x1, z2], dim=-1)
            log_det = log_s.sum(dim=-1)
            return z, log_det

        def inverse(self, z: torch.Tensor) -> torch.Tensor:
            """Inverse: z → x"""
            z1, z2 = z[:, : self.half], z[:, self.half :]
            params = self.net(z1)
            log_s, t = params.chunk(2, dim=-1)
            log_s = torch.tanh(log_s) * 2
            x2 = (z2 - t) * torch.exp(-log_s)
            return torch.cat([z1, x2], dim=-1)

    class STG_NF(nn.Module):
        """Spatio-Temporal Graph Normalizing Flow.

        Architecture:
            GCN encoder: (T, 17, 2) → (T, 17, d_gcn) → flatten → d_flat
            NF: n_flows × CouplingLayer
            Prior: N(0, I)
        """

        def __init__(
            self,
            seq_len: int = 24,
            n_joints: int = 17,
            coord_dim: int = 2,
            d_gcn: int = 32,
            n_gcn_layers: int = 2,
            n_flows: int = 4,
            nf_hidden: int = 64,
        ):
            super().__init__()
            self.seq_len = seq_len
            self.n_joints = n_joints

            # Temporal GCN encoder
            gcn_layers = [GraphConvLayer(coord_dim, d_gcn, n_joints)]
            for _ in range(n_gcn_layers - 1):
                gcn_layers.append(GraphConvLayer(d_gcn, d_gcn, n_joints))
            self.gcn = nn.ModuleList(gcn_layers)

            # Temporal aggregation: mean pool over T → (n_joints × d_gcn)
            self.d_flat = n_joints * d_gcn

            # Normalizing flow
            self.flows = nn.ModuleList(
                [CouplingLayer(self.d_flat, nf_hidden) for _ in range(n_flows)]
            )

        def encode(self, x: torch.Tensor) -> torch.Tensor:
            """GCN encode: (batch, T, 17, 2) → (batch, d_flat)"""
            B, T, J, C = x.shape
            # Reshape to (B*T, J, C) for per-frame GCN
            h = x.reshape(B * T, J, C)
            for gcn in self.gcn:
                h = gcn(h)
            # Reshape back and mean-pool over time
            h = h.reshape(B, T, J, -1).mean(dim=1)  # (B, J, d_gcn)
            return h.reshape(B, -1)  # (B, d_flat)

        def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            """Forward pass: x → z, log_prob.

            Args:
                x: (batch, T, 17, 2) skeleton sequences

            Returns:
                (z, log_prob): latent code and log probability
            """
            h = self.encode(x)
            log_det_sum = torch.zeros(h.shape[0], device=h.device)
            for flow in self.flows:
                h, log_det = flow(h)
                log_det_sum += log_det

            # Log prob under standard normal prior
            log_prior = -0.5 * (h.pow(2) + np.log(2 * np.pi)).sum(dim=-1)
            log_prob = log_prior + log_det_sum
            return h, log_prob

        def anomaly_score(self, x: torch.Tensor) -> torch.Tensor:
            """Compute anomaly score (negative log-likelihood).

            Higher score = more anomalous.
            """
            _, log_prob = self.forward(x)
            return -log_prob


class STGNFDetector:
    """Wrapper that manages pose sequence buffer and runs STG-NF inference."""

    def __init__(
        self,
        seq_len: int = 24,
        model_path: str | None = None,
        device: str = "cpu",
    ):
        self.seq_len = seq_len
        self._device = device
        self._buffers: dict[int, deque] = {}  # person_id → pose deque
        self._model: STG_NF | None = None

        if TORCH_AVAILABLE:
            try:
                self._model = STG_NF(seq_len=seq_len)
                if model_path and os.path.exists(model_path):
                    checkpoint = torch.load(model_path, map_location=device, weights_only=True)
                    self._model.load_state_dict(checkpoint["model_state_dict"])
                    logger.info("Loaded STG-NF model from %s", model_path)
                self._model.to(device)
                self._model.eval()
            except Exception:
                self._model = None

    def update(
        self,
        person_id: int,
        keypoints: np.ndarray,
        confidences: np.ndarray,
    ) -> float | None:
        """Add a pose frame and return anomaly score if buffer is full.

        Args:
            person_id: tracking ID
            keypoints: (17, 2) pixel coordinates
            confidences: (17,) per-keypoint confidence

        Returns:
            anomaly score or None if buffer not yet full
        """
        if not TORCH_AVAILABLE or self._model is None:
            return None

        # Normalize pose: center on hip midpoint, scale by torso length
        normalized = self._normalize_pose(keypoints, confidences)
        if normalized is None:
            return None

        if person_id not in self._buffers:
            self._buffers[person_id] = deque(maxlen=self.seq_len)
        self._buffers[person_id].append(normalized)

        if len(self._buffers[person_id]) < self.seq_len:
            return None

        # Run inference
        seq = np.array(list(self._buffers[person_id]))  # (T, 17, 2)
        x = torch.FloatTensor(seq).unsqueeze(0).to(self._device)

        with torch.no_grad():
            score = self._model.anomaly_score(x)
        return float(score.item())

    def evict(self, person_id: int):
        """Remove buffer for departed person."""
        self._buffers.pop(person_id, None)

    @staticmethod
    def _normalize_pose(
        keypoints: np.ndarray, confidences: np.ndarray, min_conf: float = 0.3
    ) -> np.ndarray | None:
        """Normalize to hip-centered, torso-scaled coordinates."""
        L_HIP, R_HIP = 11, 12
        L_SHOULDER, R_SHOULDER = 5, 6

        if (
            confidences[L_HIP] < min_conf
            or confidences[R_HIP] < min_conf
            or confidences[L_SHOULDER] < min_conf
            or confidences[R_SHOULDER] < min_conf
        ):
            return None

        hip_center = (keypoints[L_HIP] + keypoints[R_HIP]) / 2.0
        torso_len = np.linalg.norm(
            (keypoints[L_SHOULDER] + keypoints[R_SHOULDER]) / 2.0 - hip_center
        )
        if torso_len < 1e-6:
            return None

        normalized = np.zeros_like(keypoints)
        for i in range(17):
            if confidences[i] >= min_conf:
                normalized[i] = (keypoints[i] - hip_center) / torso_len
        return normalized
