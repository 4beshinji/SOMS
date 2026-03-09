"""Batch inference loop and retraining scheduler."""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import torch
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from config import settings
from data.extractor import DataExtractor
from data.preprocessor import Preprocessor
from model.factory import create_model
from model.trainer import Trainer
from mqtt_client import AnomalyMQTTClient
from scorer import Scorer


class Scheduler:
    def __init__(
        self,
        engine: AsyncEngine,
        mqtt_client: AnomalyMQTTClient,
        scorer: Scorer,
    ):
        self._engine = engine
        self._extractor = DataExtractor(engine)
        self._preprocessor = Preprocessor()
        self._mqtt = mqtt_client
        self._scorer = scorer
        self._trainer = Trainer(engine)
        self._running = False
        self._models: dict = {}  # zone → (model, norm_stats, model_id)

    async def start(self):
        """Start background loops."""
        self._running = True
        await self._load_active_models()
        asyncio.create_task(self._inference_loop())
        asyncio.create_task(self._retrain_loop())
        logger.info("Scheduler started")

    async def stop(self):
        self._running = False

    def get_models(self) -> dict:
        """Return loaded models info."""
        return {
            zone: {"arch": type(m).__name__, "model_id": mid}
            for zone, (m, _, mid) in self._models.items()
        }

    async def _load_active_models(self):
        """Load all active models from DB."""
        async with self._engine.begin() as conn:
            rows = await conn.execute(
                text("""
                    SELECT id, zone, arch, model_path, norm_stats
                    FROM anomaly.models
                    WHERE is_active = TRUE
                """)
            )
            for row in rows:
                model_id, zone, arch, model_path, norm_stats = row
                if not os.path.exists(model_path):
                    logger.warning("Model file missing: {}", model_path)
                    continue
                try:
                    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
                    cfg = checkpoint.get("config", {})
                    model = create_model(
                        arch=arch,
                        n_features=cfg.get("n_features", Preprocessor.N_FEATURES),
                        horizon=cfg.get("horizon", settings.HORIZON),
                        n_targets=cfg.get("n_targets", Preprocessor.N_TARGETS),
                    )
                    model.load_state_dict(checkpoint["model_state_dict"])
                    model.eval()
                    ns = checkpoint.get("norm_stats", norm_stats or {})
                    self._models[zone] = (model, ns, model_id)
                    logger.info("Loaded model for zone {} ({})", zone, arch)
                except Exception as e:
                    logger.error("Failed to load model for zone {}: {}", zone, e)

    async def _inference_loop(self):
        """Run batch inference every INFERENCE_INTERVAL seconds."""
        logger.info("Inference loop started (every {}s)", settings.INFERENCE_INTERVAL)
        while self._running:
            await asyncio.sleep(settings.INFERENCE_INTERVAL)
            if not self._running:
                break
            for zone in list(self._models.keys()):
                try:
                    await self._infer_zone(zone)
                except Exception as e:
                    logger.error("Inference failed for zone {}: {}", zone, e)

    async def _infer_zone(self, zone: str):
        """Run inference for a single zone."""
        model, norm_stats, model_id = self._models[zone]
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=settings.WINDOW_SIZE)

        series = await self._extractor.get_hourly_series(zone, start, now)
        if len(series) < settings.WINDOW_SIZE // 2:
            return  # Not enough recent data

        sensor_data, timestamps = self._preprocessor.series_to_array(series)
        sensor_data = self._preprocessor.fill_gaps(sensor_data)

        # Build means/stds from norm_stats
        means = np.zeros(Preprocessor.N_SENSOR_FEATURES)
        stds = np.ones(Preprocessor.N_SENSOR_FEATURES)
        train_stds = np.ones(Preprocessor.N_TARGETS)

        for i, channel in enumerate(Preprocessor.CHANNELS):
            for j, stat in enumerate(Preprocessor.STATS):
                key = f"{stat}_{channel}"
                idx = i * len(Preprocessor.STATS) + j
                if key in norm_stats:
                    means[idx] = norm_stats[key]["mean"]
                    stds[idx] = norm_stats[key]["std"] if norm_stats[key]["std"] > 0 else 1.0
            # Training std for avg channel (for scoring)
            avg_key = f"avg_{channel}"
            if avg_key in norm_stats and norm_stats[avg_key]["std"] > 0:
                train_stds[i] = norm_stats[avg_key]["std"]

        sensor_norm = (sensor_data - means) / stds
        temporal = self._preprocessor.add_temporal(timestamps)
        full_data = np.concatenate([sensor_norm, temporal], axis=1)

        # Pad or trim to window size
        window = settings.WINDOW_SIZE
        if full_data.shape[0] >= window:
            input_data = full_data[-window:]
        else:
            input_data = np.zeros((window, Preprocessor.N_FEATURES))
            input_data[-full_data.shape[0] :] = full_data

        # Inference
        model.eval()
        with torch.no_grad():
            x = torch.FloatTensor(input_data).unsqueeze(0)
            pred = model(x)  # (1, horizon, n_targets)

        # Compare first prediction step with most recent actual
        predicted = pred[0, 0, :].numpy()
        # Actual = last row's avg values (already normalized)
        actual = np.array(
            [input_data[-1, i * 3] for i in range(Preprocessor.N_TARGETS)]
        )

        results = self._scorer.compute_scores(
            predicted=predicted,
            actual=actual,
            train_stds=np.ones(Preprocessor.N_TARGETS),  # Already in z-score space
            zone=zone,
            channels=Preprocessor.CHANNELS,
            source="batch",
        )

        # Publish and record
        for result in results:
            self._mqtt.publish_anomaly(result)
            await self._record_detection(result, model_id)

    async def _record_detection(self, result, model_id: int):
        """Write detection to anomaly.detections table."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text("""
                    INSERT INTO anomaly.detections
                        (zone, channel, score, predicted, actual, severity, source, model_id)
                    VALUES
                        (:zone, :channel, :score, :predicted, :actual, :severity, :source, :model_id)
                """),
                {
                    "zone": result.zone,
                    "channel": result.channel,
                    "score": result.score,
                    "predicted": result.predicted,
                    "actual": result.actual,
                    "severity": result.severity,
                    "source": result.source,
                    "model_id": model_id,
                },
            )

    async def _retrain_loop(self):
        """Weekly retraining on configured day/hour."""
        logger.info("Retrain loop started (day={} hour={})", settings.RETRAIN_DAY, settings.RETRAIN_HOUR_UTC)
        while self._running:
            await asyncio.sleep(3600)  # Check every hour
            if not self._running:
                break
            now = datetime.now(timezone.utc)
            if now.weekday() == settings.RETRAIN_DAY and now.hour == settings.RETRAIN_HOUR_UTC:
                logger.info("Starting scheduled retraining")
                try:
                    results = await self._trainer.train_all_zones()
                    logger.info("Retrained {} zones", len(results))
                    await self._load_active_models()
                except Exception as e:
                    logger.error("Retrain failed: {}", e)
