"""SwitchBot Cloud Bridge — entry point.

Bridges SwitchBot Cloud API v1.1 devices into SOMS via MQTT,
using the same telemetry and MCP protocol as ESP32 edge devices.
"""

import asyncio
import logging
import os
import signal
import sys

from aiohttp import web
from config_loader import load_config
from switchbot_api import SwitchBotAPI
from mqtt_bridge import MQTTBridge
from device_manager import DeviceManager
from webhook_server import WebhookServer

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("SwitchBotBridge")


async def start_health_server(mqtt_bridge: MQTTBridge, port: int = 8080):
    """Start lightweight aiohttp health endpoint."""
    async def _health(request):
        checks = {}
        checks["mqtt"] = "ok" if mqtt_bridge._connected else "error: disconnected"
        all_ok = all(v == "ok" for v in checks.values())
        return web.json_response(
            {"status": "healthy" if all_ok else "degraded", "service": "switchbot", "checks": checks},
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
    logger.info("Starting SwitchBot Cloud Bridge...")

    # Load config
    config_path = os.getenv("SWITCHBOT_CONFIG", "/app/config/switchbot.yaml")
    config = load_config(config_path)

    # API client
    api_cfg = config.get("api", {})
    token = api_cfg.get("token") or os.getenv("SWITCHBOT_TOKEN", "")
    secret = api_cfg.get("secret") or os.getenv("SWITCHBOT_SECRET", "")
    if not token or not secret:
        logger.error("SWITCHBOT_TOKEN and SWITCHBOT_SECRET must be set")
        sys.exit(1)

    api = SwitchBotAPI(token, secret)

    # MQTT
    mqtt = MQTTBridge()

    # Device manager
    dm = DeviceManager(config, api, mqtt)
    dm.create_devices()

    if not dm.devices:
        logger.warning("No devices configured — bridge will run but do nothing")

    # Connect MQTT (blocking retry inside)
    mqtt.connect()

    # Start health check HTTP server
    health_port = int(os.getenv("HEALTH_PORT", "8080"))
    await start_health_server(mqtt, health_port)

    # Build async tasks
    tasks = [
        asyncio.create_task(dm.poll_loop()),
        asyncio.create_task(dm.heartbeat_loop()),
    ]

    # Optional webhook server
    webhook_cfg = config.get("webhook", {})
    if webhook_cfg.get("enabled", False):
        port = webhook_cfg.get("port", 8005)
        webhook = WebhookServer(port, dm)
        await webhook.start()
        logger.info(f"Webhook server enabled on port {port}")

    # Graceful shutdown
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    logger.info(f"SwitchBot Bridge running ({len(dm.devices)} devices)")
    await stop_event.wait()

    # Cleanup
    logger.info("Shutting down...")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await api.close()
    mqtt.stop()
    logger.info("SwitchBot Bridge stopped")


if __name__ == "__main__":
    asyncio.run(main())
