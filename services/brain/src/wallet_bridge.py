"""WalletBridge: MQTT heartbeat → Wallet REST API relay.

Forwards device heartbeats to the Wallet service so that mesh leaf devices
(which cannot make REST calls directly) still receive infrastructure rewards.
Includes device metrics and utility_score from the DeviceRegistry.
"""

import os
import time
import logging

logger = logging.getLogger(__name__)


class WalletBridge:
    def __init__(self, session, device_registry):
        self.session = session
        self.device_registry = device_registry
        self.wallet_url = os.getenv("WALLET_SERVICE_URL", "http://wallet:8000")
        self._service_token = os.getenv("INTERNAL_SERVICE_TOKEN", "")
        self._last_forwarded: dict[str, float] = {}
        self.forward_interval = 300  # 5 min throttle

    def _service_headers(self) -> dict:
        """Return headers for authenticated service-to-service calls."""
        return {"X-Service-Token": self._service_token} if self._service_token else {}

    async def forward_heartbeat(self, device_id: str, payload: dict):
        """Forward a heartbeat to Wallet service with DeviceRegistry metrics.

        Throttled to at most once per forward_interval per device.
        """
        now = time.time()
        last = self._last_forwarded.get(device_id, 0)
        if now - last < self.forward_interval:
            return

        device_info = self.device_registry.get_device(device_id)
        body = {}
        if device_info:
            body["power_mode"] = device_info.power_mode
            body["battery_pct"] = device_info.battery_pct
            body["hops_to_mqtt"] = device_info.hops_to_mqtt
            body["utility_score"] = device_info.utility_score

        url = f"{self.wallet_url}/devices/{device_id}/heartbeat"
        try:
            async with self.session.post(url, json=body, headers=self._service_headers(), timeout=10) as resp:
                if resp.status == 200:
                    self._last_forwarded[device_id] = now
                    logger.debug("Heartbeat forwarded: %s → Wallet", device_id)
                elif resp.status == 404:
                    # Device not registered — auto-register then retry
                    registered = await self._auto_register_device(
                        device_id, payload, device_info,
                    )
                    if registered:
                        # Retry heartbeat after registration
                        async with self.session.post(url, json=body, headers=self._service_headers(), timeout=10) as retry_resp:
                            if retry_resp.status == 200:
                                logger.info("Heartbeat forwarded after auto-register: %s", device_id)
                    self._last_forwarded[device_id] = now
                else:
                    text = await resp.text()
                    logger.warning(
                        "Heartbeat forward failed: %s → %d %s",
                        device_id, resp.status, text[:200],
                    )
        except Exception as e:
            # Connection errors: throttle 60s to avoid log spam, allow retry
            self._last_forwarded[device_id] = now - self.forward_interval + 60
            logger.warning("Heartbeat forward error: %s → %s", device_id, e)

    async def _auto_register_device(
        self, device_id: str, payload: dict, device_info=None,
    ) -> bool:
        """Register a device in Wallet service (system wallet as owner)."""
        device_type = "sensor_node"
        if device_info:
            device_type = device_info.device_type or "sensor_node"
        elif "device_type" in payload:
            device_type = payload["device_type"]

        display_name = payload.get("label", "") or device_id
        topic_prefix = f"office/{payload.get('zone', 'unknown')}/sensor/{device_id}"

        body = {
            "device_id": device_id,
            "owner_id": 0,  # system wallet
            "device_type": device_type,
            "display_name": display_name,
            "topic_prefix": topic_prefix,
        }
        url = f"{self.wallet_url}/devices/"
        try:
            async with self.session.post(url, json=body, headers=self._service_headers(), timeout=10) as resp:
                if resp.status in (200, 201):
                    logger.info("Auto-registered device in Wallet: %s (%s)", device_id, display_name)
                    return True
                elif resp.status == 409:
                    # Already exists (race condition) — that's fine
                    return True
                else:
                    text = await resp.text()
                    logger.warning("Device auto-register failed: %s → %d %s", device_id, resp.status, text[:200])
                    return False
        except Exception as e:
            logger.warning("Device auto-register error: %s → %s", device_id, e)
            return False

    async def forward_children(self, parent_id: str, payload: dict):
        """Forward heartbeats for child devices listed in the payload."""
        children = payload.get("children", [])
        for child_data in children:
            child_id = child_data.get("device_id")
            if not child_id:
                continue
            # Use dot notation for child IDs
            if "." not in child_id and "." not in parent_id:
                full_child_id = f"{parent_id}.{child_id}"
            else:
                full_child_id = child_id
            await self.forward_heartbeat(full_child_id, child_data)
