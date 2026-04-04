"""Anomaly detection service — FastAPI entry point with background loops."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from config import settings
from database import engine, init_db
from data.preprocessor import Preprocessor
from model.trainer import Trainer
from mqtt_client import AnomalyMQTTClient
from realtime import RealtimeDetector
from routers import admin, status
from scheduler import Scheduler
from scorer import Scorer


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    await init_db()

    scorer = Scorer()
    preprocessor = Preprocessor()

    # Realtime detector (created before MQTT so we can pass the callback)
    realtime = RealtimeDetector(
        models={},
        preprocessor=preprocessor,
        scorer=scorer,
        mqtt_client=None,  # Set after mqtt_client is created
    )

    # MQTT client with realtime callback
    mqtt_callback = realtime.on_sensor_message if settings.REALTIME_ENABLED else None
    mqtt_client = AnomalyMQTTClient(on_sensor_message=mqtt_callback)
    mqtt_client.connect()
    realtime._mqtt = mqtt_client

    # Trainer
    trainer = Trainer(engine)

    # Scheduler (batch inference + retrain)
    scheduler = Scheduler(engine, mqtt_client, scorer)
    await scheduler.start()

    # Share loaded models with realtime detector
    realtime._models = {
        zone: (m, ns) for zone, (m, ns, _) in scheduler._models.items()
    }

    # Wire up routers
    status.set_scheduler(scheduler)
    status.set_mqtt_client(mqtt_client)
    admin.set_trainer(trainer)

    logger.info("Anomaly detection service started (arch={}, realtime={})",
                settings.MODEL_ARCH, settings.REALTIME_ENABLED)

    yield

    # --- Shutdown ---
    await scheduler.stop()
    mqtt_client.disconnect()
    logger.info("Anomaly detection service stopped")


app = FastAPI(title="SOMS Anomaly Detection", lifespan=lifespan)
app.include_router(status.router)
app.include_router(admin.router)
