"""Optional: SwitchBot Webhook receiver for real-time event push.

When enabled, SwitchBot Cloud pushes events (motion detected, door opened, etc.)
instead of relying solely on polling. This reduces latency for event-driven sensors.
"""

import logging

from aiohttp import web

logger = logging.getLogger(__name__)


class WebhookServer:
    """Lightweight aiohttp server for SwitchBot webhook callbacks."""

    def __init__(self, port: int, device_manager):
        self._port = port
        self._dm = device_manager
        self._app = web.Application()
        self._app.router.add_post("/switchbot/webhook", self._handle_webhook)
        self._app.router.add_get("/health", self._health)

    async def start(self):
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self._port)
        await site.start()
        logger.info(f"Webhook server listening on port {self._port}")

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming SwitchBot webhook event."""
        try:
            data = await request.json()
            logger.info(f"Webhook event: {data}")

            event_type = data.get("eventType")
            event_version = data.get("eventVersion")
            context = data.get("context", {})

            # Find matching device by SwitchBot device MAC
            device_mac = context.get("deviceMac", "")
            for device in self._dm.devices.values():
                if device.switchbot_id.replace(":", "").upper() == device_mac.replace(":", "").upper():
                    # Convert webhook context to status-like dict and publish
                    channels = device.status_to_channels(context)
                    if channels:
                        device.publish_channels(channels)
                    logger.info(f"Webhook routed to {device.soms_device_id}")
                    break
            else:
                logger.warning(f"No device found for webhook MAC: {device_mac}")

            return web.json_response({"status": "ok"})
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "healthy"})
