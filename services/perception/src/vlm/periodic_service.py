"""
VLM Periodic Service — runs scheduled scene analysis across zones.
Registered via scheduler.register_service() like MTMCPublisher.
"""
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class VLMPeriodicService:
    """Periodically captures frames from each zone and requests VLM scene analysis."""

    def __init__(self, vlm_analyzer, image_sources: dict, interval_sec: float = 300):
        self._analyzer = vlm_analyzer
        self._sources = image_sources  # {zone_name: ImageSource}
        self._interval = interval_sec

    async def run(self):
        """Infinite loop: cycle through zones with staggered timing."""
        zones = list(self._sources.keys())
        if not zones:
            logger.warning("VLMPeriodicService: no image sources, exiting")
            return

        per_zone_delay = self._interval / len(zones)
        logger.info(
            "VLMPeriodicService started: %d zones, interval=%.0fs, per-zone=%.0fs",
            len(zones), self._interval, per_zone_delay,
        )

        while True:
            for zone_name in zones:
                try:
                    source = self._sources[zone_name]
                    frame = await asyncio.to_thread(source.read)
                    if frame is None:
                        logger.debug("VLMPeriodic: no frame from %s, skipping", zone_name)
                        await asyncio.sleep(per_zone_delay)
                        continue

                    await self._analyzer.request_analysis(
                        frame, "scene", zone_name, {"trigger": "periodic"},
                    )
                except Exception:
                    logger.exception("VLMPeriodic error for zone %s", zone_name)

                await asyncio.sleep(per_zone_delay)
