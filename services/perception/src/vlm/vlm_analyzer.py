"""
VLM Analyzer — rate-limited analysis component.
Follows the same pattern as VADMonitor: not a MonitorBase subclass,
but a processing component called from existing monitors.
"""
import asyncio
import logging
import time
from typing import Dict, Optional

import numpy as np

from state_publisher import StatePublisher
from vlm.vlm_client import VLMClient
from vlm.prompt_templates import get_prompt

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWNS = {
    "scene": 300,
    "occupancy_change": 60,
    "fall_candidate": 30,
    "unusual_activity": 300,
}


class VLMAnalyzer:
    """Rate-limited VLM analysis with async execution and MQTT publishing."""

    def __init__(
        self,
        vlm_client: VLMClient,
        publisher: StatePublisher,
        cooldowns: Optional[Dict[str, float]] = None,
        enabled: bool = True,
    ):
        self._client = vlm_client
        self._publisher = publisher
        self._cooldowns = cooldowns or DEFAULT_COOLDOWNS
        self._enabled = enabled
        self._last_analysis: Dict[str, float] = {}  # (zone, type) -> timestamp
        self._pending: set = set()  # track in-flight tasks

    def _cooldown_key(self, zone: str, analysis_type: str) -> str:
        return f"{zone}:{analysis_type}"

    def _is_cooled_down(self, zone: str, analysis_type: str) -> bool:
        key = self._cooldown_key(zone, analysis_type)
        last = self._last_analysis.get(key, 0)
        cooldown = self._cooldowns.get(analysis_type, 300)
        return (time.time() - last) >= cooldown

    async def request_analysis(
        self,
        frame: np.ndarray,
        analysis_type: str,
        zone: str,
        context: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Request a VLM analysis. Returns None if disabled or rate-limited.
        Runs the actual VLM call asynchronously via create_task.
        """
        if not self._enabled:
            return None

        if not self._is_cooled_down(zone, analysis_type):
            logger.debug("VLM cooldown active for %s/%s", zone, analysis_type)
            return None

        key = self._cooldown_key(zone, analysis_type)

        # Prevent duplicate in-flight requests
        if key in self._pending:
            return None

        # Mark cooldown immediately to prevent burst
        self._last_analysis[key] = time.time()
        self._pending.add(key)

        # Fire and forget
        asyncio.create_task(self._run_analysis(frame, analysis_type, zone, context or {}, key))
        return {"status": "queued", "analysis_type": analysis_type, "zone": zone}

    async def _run_analysis(
        self,
        frame: np.ndarray,
        analysis_type: str,
        zone: str,
        context: dict,
        pending_key: str,
    ):
        try:
            prompt_ctx = {"zone": zone, **context}
            prompt = get_prompt(analysis_type, **prompt_ctx)
            response = await self._client.analyze(frame, prompt)

            if response.error:
                logger.error("VLM analysis failed [%s/%s]: %s", zone, analysis_type, response.error)
                return

            payload = {
                "analysis_type": analysis_type,
                "trigger": context.get("trigger", "event"),
                "content": response.content,
                "model": response.model,
                "latency_sec": response.latency_sec,
                "timestamp": time.time(),
            }

            topic = f"office/{zone}/vlm/{analysis_type}"
            await self._publisher.publish(topic, payload)
            logger.info(
                "VLM analysis [%s/%s]: %.1fs — %s",
                zone, analysis_type, response.latency_sec,
                response.content[:80],
            )
        except Exception:
            logger.exception("VLM analysis error [%s/%s]", zone, analysis_type)
        finally:
            self._pending.discard(pending_key)
