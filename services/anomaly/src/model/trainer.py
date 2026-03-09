"""Training loop for anomaly detection models."""
import json
import os
from datetime import datetime, timezone

import numpy as np
import torch
import torch.nn as nn
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from config import settings
from data.extractor import DataExtractor
from data.preprocessor import Preprocessor
from model.factory import create_model


class Trainer:
    def __init__(self, engine: AsyncEngine):
        self._engine = engine
        self._extractor = DataExtractor(engine)
        self._preprocessor = Preprocessor()

    async def train_zone(self, zone: str) -> dict | None:
        """Train a model for a single zone.

        Returns:
            Training result dict or None if insufficient data.
        """
        coverage = await self._extractor.get_data_coverage(zone)
        if coverage["days"] < settings.MIN_DATA_DAYS:
            logger.warning(
                "Zone {} has only {:.1f} days of data (need {}), skipping",
                zone,
                coverage["days"],
                settings.MIN_DATA_DAYS,
            )
            return None

        # Fetch all available data
        start = datetime.fromisoformat(coverage["earliest"])
        end = datetime.fromisoformat(coverage["latest"])
        series = await self._extractor.get_hourly_series(zone, start, end)

        if not series:
            return None

        # Prepare data
        result = self._preprocessor.prepare_training_data(
            series, window=settings.WINDOW_SIZE, horizon=settings.HORIZON
        )
        if result is None:
            logger.warning("Zone {}: insufficient data after preprocessing", zone)
            return None

        X, Y, means, stds = result

        # Split: last 2 weeks = validation
        val_size = min(14 * 24, X.shape[0] // 5)
        X_train, X_val = X[:-val_size], X[-val_size:]
        Y_train, Y_val = Y[:-val_size], Y[-val_size:]

        logger.info(
            "Zone {}: {} train, {} val samples", zone, X_train.shape[0], X_val.shape[0]
        )

        # Create model
        model = create_model(
            arch=settings.MODEL_ARCH,
            n_features=Preprocessor.N_FEATURES,
            horizon=settings.HORIZON,
            n_targets=Preprocessor.N_TARGETS,
        )

        # Training loop
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        criterion = nn.MSELoss()

        X_train_t = torch.FloatTensor(X_train)
        Y_train_t = torch.FloatTensor(Y_train)
        X_val_t = torch.FloatTensor(X_val)
        Y_val_t = torch.FloatTensor(Y_val)

        best_val_loss = float("inf")
        best_state = None
        patience = 10
        patience_counter = 0
        epoch = 0
        max_epochs = 100

        model.train()
        for epoch in range(1, max_epochs + 1):
            # Mini-batch training
            batch_size = 32
            indices = torch.randperm(X_train_t.shape[0])
            total_loss = 0
            n_batches = 0

            for start_idx in range(0, X_train_t.shape[0], batch_size):
                batch_idx = indices[start_idx : start_idx + batch_size]
                x_batch = X_train_t[batch_idx]
                y_batch = Y_train_t[batch_idx]

                optimizer.zero_grad()
                pred = model(x_batch)
                loss = criterion(pred, y_batch)
                loss.backward()
                optimizer.step()

                total_loss += loss.item()
                n_batches += 1

            train_loss = total_loss / max(n_batches, 1)

            # Validation
            model.eval()
            with torch.no_grad():
                val_pred = model(X_val_t)
                val_loss = criterion(val_pred, Y_val_t).item()
            model.train()

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
                patience_counter = 0
            else:
                patience_counter += 1

            if epoch % 10 == 0:
                logger.info(
                    "Zone {} epoch {}: train={:.6f} val={:.6f}", zone, epoch, train_loss, val_loss
                )

            if patience_counter >= patience:
                logger.info("Zone {}: early stopping at epoch {}", zone, epoch)
                break

        # Restore best model
        if best_state:
            model.load_state_dict(best_state)

        # Save checkpoint
        version = datetime.now(timezone.utc)
        arch_name = type(model).__name__.replace("Forecaster", "").lower()
        model_dir = os.path.join(settings.MODEL_STORE_PATH, zone)
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, f"{version.strftime('%Y%m%dT%H%M%S')}.pt")

        norm_stats = {}
        for i, channel in enumerate(Preprocessor.CHANNELS):
            for j, stat in enumerate(Preprocessor.STATS):
                idx = i * len(Preprocessor.STATS) + j
                norm_stats[f"{stat}_{channel}"] = {
                    "mean": float(means[idx]),
                    "std": float(stds[idx]),
                }

        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "norm_stats": norm_stats,
                "config": {
                    "arch": arch_name,
                    "n_features": Preprocessor.N_FEATURES,
                    "horizon": settings.HORIZON,
                    "n_targets": Preprocessor.N_TARGETS,
                    "window_size": settings.WINDOW_SIZE,
                },
                "training_meta": {
                    "zone": zone,
                    "epochs": epoch,
                    "val_loss": best_val_loss,
                    "train_samples": X_train.shape[0],
                    "val_samples": X_val.shape[0],
                    "version": version.isoformat(),
                },
            },
            model_path,
        )

        # Register in DB and auto-promote
        await self._register_model(
            zone=zone,
            arch=arch_name,
            version=version,
            val_loss=best_val_loss,
            epochs=epoch,
            norm_stats=norm_stats,
            model_path=model_path,
        )

        return {
            "zone": zone,
            "arch": arch_name,
            "epochs": epoch,
            "val_loss": best_val_loss,
            "model_path": model_path,
        }

    async def _register_model(
        self, zone, arch, version, val_loss, epochs, norm_stats, model_path
    ):
        """Register model in DB. Auto-promote if val_loss is within 110% of current best."""
        async with self._engine.begin() as conn:
            # Check current active model
            row = await conn.execute(
                text("""
                    SELECT id, val_loss FROM anomaly.models
                    WHERE zone = :zone AND is_active = TRUE
                    LIMIT 1
                """),
                {"zone": zone},
            )
            current = row.fetchone()

            promote = True
            if current and current[1] is not None:
                # Only promote if new model is within 110% of current
                if val_loss > current[1] * 1.1:
                    promote = False
                    logger.warning(
                        "Zone {}: new val_loss {:.6f} > 110% of current {:.6f}, not promoting",
                        zone,
                        val_loss,
                        current[1],
                    )

            if promote and current:
                await conn.execute(
                    text("UPDATE anomaly.models SET is_active = FALSE WHERE id = :id"),
                    {"id": current[0]},
                )

            await conn.execute(
                text("""
                    INSERT INTO anomaly.models
                        (zone, arch, version, val_loss, epochs, norm_stats, model_path, is_active)
                    VALUES
                        (:zone, :arch, :version, :val_loss, :epochs,
                         CAST(:norm_stats AS jsonb), :model_path, :is_active)
                """),
                {
                    "zone": zone,
                    "arch": arch,
                    "version": version,
                    "val_loss": val_loss,
                    "epochs": epochs,
                    "norm_stats": json.dumps(norm_stats),
                    "model_path": model_path,
                    "is_active": promote,
                },
            )

    async def train_all_zones(self) -> list[dict]:
        """Train models for all zones with sufficient data."""
        zones = await self._extractor.get_available_zones()
        results = []
        for zone in zones:
            try:
                result = await self.train_zone(zone)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error("Training failed for zone {}: {}", zone, e)
        return results
