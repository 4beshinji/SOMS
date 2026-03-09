"""Training utilities for VAD models.

All three models train on **normal data only** (one-class learning):
- STG-NF: normal pose sequences → learn distribution of normal poses
- AED-MAE: normal frames → learn to reconstruct normal scenes
- AI-VAD: normal attributes → fit Gaussian density per feature stream

Training data collection:
  Runs in "learning mode" for a configurable period, collecting normal data
  from the perception pipeline. After sufficient data, trains all models.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, TensorDataset

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class VADTrainer:
    """Collects normal data and trains all three VAD models."""

    def __init__(self, model_dir: str = "/app/model_store/vad"):
        self._model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)

        # Collection buffers
        self._pose_sequences: list[np.ndarray] = []  # (T, 17, 2) each
        self._frames: list[np.ndarray] = []           # (H, W, 3) each
        self._velocity_data: list[np.ndarray] = []    # (3,) each
        self._pose_features: list[np.ndarray] = []    # (34,) each
        self._appearance_features: list[np.ndarray] = []  # (64,) each

        self._collecting = False
        self._collection_start: float = 0
        self._min_samples = 500

    def start_collection(self):
        """Start collecting normal data."""
        self._collecting = True
        self._collection_start = time.time()
        logger.info("VAD training: started normal data collection")

    def stop_collection(self):
        """Stop collection."""
        self._collecting = False
        logger.info(
            "VAD training: stopped collection (poses=%d, frames=%d, attrs=%d)",
            len(self._pose_sequences),
            len(self._frames),
            len(self._velocity_data),
        )

    @property
    def is_collecting(self) -> bool:
        return self._collecting

    def add_pose_sequence(self, seq: np.ndarray):
        """Add a normalized pose sequence (T, 17, 2)."""
        if self._collecting:
            self._pose_sequences.append(seq)

    def add_frame(self, frame: np.ndarray):
        """Add a normal frame (H, W, 3)."""
        if self._collecting and len(self._frames) < 10000:
            self._frames.append(frame)

    def add_attributes(
        self,
        velocity: np.ndarray,
        pose_features: np.ndarray,
        appearance: np.ndarray | None,
    ):
        """Add normal attribute vectors."""
        if not self._collecting:
            return
        self._velocity_data.append(velocity)
        self._pose_features.append(pose_features)
        if appearance is not None:
            self._appearance_features.append(appearance)

    def train_all(self) -> dict:
        """Train all three models on collected normal data."""
        results = {}

        if len(self._pose_sequences) >= self._min_samples:
            results["stg_nf"] = self._train_stg_nf()
        else:
            logger.warning(
                "STG-NF: insufficient pose data (%d < %d)",
                len(self._pose_sequences), self._min_samples,
            )

        if len(self._frames) >= 100:
            results["aed_mae"] = self._train_aed_mae()
        else:
            logger.warning("AED-MAE: insufficient frames (%d)", len(self._frames))

        if len(self._velocity_data) >= self._min_samples:
            results["attribute_vad"] = self._train_attribute_vad()
        else:
            logger.warning(
                "AI-VAD: insufficient attribute data (%d)", len(self._velocity_data)
            )

        return results

    def _train_stg_nf(self) -> dict:
        """Train STG-NF normalizing flow on normal pose sequences."""
        if not TORCH_AVAILABLE:
            return {"status": "skipped", "reason": "torch unavailable"}

        from vad.stg_nf import STG_NF

        seq_len = 24
        # Stack sequences
        data = np.array(self._pose_sequences)  # (N, T, 17, 2)
        if data.shape[1] != seq_len:
            logger.warning("STG-NF: sequence length mismatch, reshaping")
            return {"status": "error", "reason": "sequence length mismatch"}

        dataset = TensorDataset(torch.FloatTensor(data))
        loader = DataLoader(dataset, batch_size=32, shuffle=True)

        model = STG_NF(seq_len=seq_len)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

        model.train()
        best_loss = float("inf")
        for epoch in range(50):
            total_loss = 0
            for (batch,) in loader:
                optimizer.zero_grad()
                _, log_prob = model(batch)
                loss = -log_prob.mean()  # Maximize log-likelihood
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

            avg_loss = total_loss / len(loader)
            if avg_loss < best_loss:
                best_loss = avg_loss

            if epoch % 10 == 0:
                logger.info("STG-NF epoch %d: loss=%.4f", epoch, avg_loss)

        path = os.path.join(self._model_dir, "stg_nf.pt")
        torch.save({"model_state_dict": model.state_dict()}, path)
        logger.info("STG-NF model saved to %s", path)
        return {"status": "ok", "loss": best_loss, "samples": len(data)}

    def _train_aed_mae(self) -> dict:
        """Train AED-MAE on normal frames."""
        if not TORCH_AVAILABLE:
            return {"status": "skipped", "reason": "torch unavailable"}

        import cv2
        from vad.aed_mae import AED_MAE

        img_size = 64
        # Preprocess frames
        tensors = []
        for frame in self._frames:
            resized = cv2.resize(frame, (img_size, img_size))
            t = torch.FloatTensor(resized).permute(2, 0, 1) / 255.0
            tensors.append(t)

        data = torch.stack(tensors)
        dataset = TensorDataset(data)
        loader = DataLoader(dataset, batch_size=32, shuffle=True)

        model = AED_MAE(img_size=img_size)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

        model.train()
        best_loss = float("inf")
        running_stats = {"mean": 0.0, "var": 1.0, "count": 0}

        for epoch in range(30):
            total_loss = 0
            for (batch,) in loader:
                optimizer.zero_grad()
                recon, target, _ = model(batch)
                loss = F.mse_loss(recon, target)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

                # Collect running stats for Z-scoring during inference
                with torch.no_grad():
                    scores = F.mse_loss(recon, target, reduction="none").mean(dim=(1, 2))
                    for s in scores:
                        n = running_stats["count"] + 1
                        old_m = running_stats["mean"]
                        val = s.item()
                        new_m = old_m + (val - old_m) / n
                        new_v = running_stats["var"] * (n - 1) / max(n, 1) + (val - old_m) * (val - new_m) / max(n, 1)
                        running_stats = {"mean": new_m, "var": new_v, "count": n}

            avg_loss = total_loss / len(loader)
            if avg_loss < best_loss:
                best_loss = avg_loss

            if epoch % 10 == 0:
                logger.info("AED-MAE epoch %d: loss=%.6f", epoch, avg_loss)

        path = os.path.join(self._model_dir, "aed_mae.pt")
        torch.save({
            "model_state_dict": model.state_dict(),
            "running_stats": running_stats,
        }, path)
        logger.info("AED-MAE model saved to %s", path)
        return {"status": "ok", "loss": best_loss, "samples": len(data)}

    def _train_attribute_vad(self) -> dict:
        """Fit Gaussian density estimators on normal attribute data."""
        from vad.attribute_vad import AttributeVADDetector, GaussianDensity

        detector = AttributeVADDetector()

        # Fit velocity density
        vel_data = np.array(self._velocity_data)
        detector._velocity_density.fit(vel_data)

        # Fit pose density
        pose_data = np.array(self._pose_features)
        detector._pose_density.fit(pose_data)

        # Fit appearance density (if available)
        if self._appearance_features:
            app_data = np.array(self._appearance_features)
            detector._appearance_density.fit(app_data)

        path = os.path.join(self._model_dir, "attribute_vad.pt")
        detector.save(path)
        logger.info("AttributeVAD model saved to %s", path)
        return {
            "status": "ok",
            "samples": len(vel_data),
            "velocity_fitted": True,
            "pose_fitted": True,
            "appearance_fitted": len(self._appearance_features) > 0,
        }
