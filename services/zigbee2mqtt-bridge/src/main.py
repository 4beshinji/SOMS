"""Zigbee2MQTT Bridge — entry point.

Bridges Zigbee2MQTT devices into SOMS via MQTT topic translation,
using the same telemetry and MCP protocol as ESP32 edge devices.
No API client or polling needed — Z2M is MQTT-native.
"""

import asyncio
import logging
import os
import signal
import sys

from aiohttp import web
from config_loader import load_config
from mqtt_bridge import MQTTBridge
from device_manager import DeviceManager

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Zigbee2MQTTBridge")


async def start_health_server(mqtt_bridge: MQTTBridge, port: int = 8080):
    """Start lightweight aiohttp health endpoint."""
    async def _health(request):
        checks = {}
        checks["mqtt"] = "ok" if mqtt_bridge._connected else "error: disconnected"
        all_ok = all(v == "ok" for v in checks.values())
        return web.json_response(
            {"status": "healthy" if all_ok else "degraded", "service": "zigbee2mqtt-bridge", "checks": checks},
            status=200 if all_ok else 503,
        )

    app = web.Application()
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health server listening on :{port}")


async def main():
    logger.info("Starting Zigbee2MQTT Bridge...")

    # Load config
    config_path = os.getenv("Z2M_BRIDGE_CONFIG", "/app/config/zigbee2mqtt-bridge.yaml")
    config = load_config(config_path)

    # Z2M base topic (default: zigbee2mqtt)
    z2m_base_topic = config.get("z2m_base_topic", "zigbee2mqtt")

    # MQTT
    mqtt = MQTTBridge(z2m_base_topic=z2m_base_topic)

    # Device manager (no API client — Z2M pushes state)
    dm = DeviceManager(config, mqtt)

    # Sync zone assignments from spatial config (ZoneEditor placements)
    spatial_overrides = await dm.sync_zones_from_spatial()
    dm.create_devices(spatial_overrides=spatial_overrides)

    if not dm.devices:
        logger.warning("No devices configured — bridge will run but do nothing")

    # Wire auto-discovery: when Z2M publishes bridge/devices, auto-register unknowns
    mqtt._on_bridge_devices = dm.handle_bridge_devices

    # Connect MQTT (blocking retry inside)
    mqtt.connect()

    # Start health check HTTP server
    health_port = int(os.getenv("HEALTH_PORT", "8080"))
    await start_health_server(mqtt, health_port)

    # Build async tasks
    tasks = [
        asyncio.create_task(dm.heartbeat_loop()),
        asyncio.create_task(dm.flush_loop()),
    ]

    # Graceful shutdown
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    logger.info(f"Zigbee2MQTT Bridge running ({len(dm.devices)} devices)")
    await stop_event.wait()

    # Cleanup
    logger.info("Shutting down...")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    mqtt.stop()
    logger.info("Zigbee2MQTT Bridge stopped")


if __name__ == "__main__":
    asyncio.run(main())
