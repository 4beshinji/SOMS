"""
MTMC Publisher — periodically publishes global tracking state to MQTT.

Publishes:
  - office/tracking/persons: All tracked persons across all cameras
  - office/{zone}/tracking: Per-zone person summaries

When VADMonitor is attached, each person entry includes:
  - crime_coefficient: float (0-300)
  - threat_level: str ("clear"|"latent"|"warning"|"critical")
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tracking.cross_camera_tracker import CrossCameraTracker
    from vad.vad_monitor import VADMonitor

from state_publisher import StatePublisher

logger = logging.getLogger(__name__)


class MTMCPublisher:
    """Publishes global tracking data at a fixed interval."""

    def __init__(
        self,
        tracker: CrossCameraTracker,
        publish_interval_sec: float = 0.5,
        vad_monitor: VADMonitor | None = None,
    ):
        self._tracker = tracker
        self._interval = publish_interval_sec
        self._publisher = StatePublisher.get_instance()
        self._running = True
        self._vad = vad_monitor

    async def run(self):
        """Main loop: publish global tracks at fixed interval (2Hz default)."""
        logger.info(
            "MTMCPublisher started (interval=%.1fs)", self._interval
        )

        while self._running:
            try:
                await self._publish_cycle()
            except Exception as e:
                logger.error("MTMCPublisher error: %s", e, exc_info=True)

            await asyncio.sleep(self._interval)

    async def _publish_cycle(self):
        timestamp = time.time()
        tracks = self._tracker.get_global_tracks()
        zone_counts = self._tracker.get_person_count_by_zone()

        # Build persons list
        persons = []
        for track in tracks:
            person = {
                "global_id": track.global_id,
                "floor_x_m": track.floor_position[0],
                "floor_y_m": track.floor_position[1],
                "zone": track.zone_id,
                "cameras": track.camera_ids,
                "sources": track.source_ids,
                "confidence": max(
                    (
                        t.detections[-1].confidence
                        for t in track.tracklets.values()
                        if t.detections
                    ),
                    default=0.0,
                ),
                "duration_sec": track.duration_sec,
            }

            # Attach crime coefficient from VADMonitor
            if self._vad is not None:
                breakdown = self._vad.get_breakdown(track.global_id)
                if breakdown:
                    person["crime_coefficient"] = breakdown["crime_coefficient"]
                    person["threat_level"] = breakdown["severity"]
                else:
                    person["crime_coefficient"] = 0.0
                    person["threat_level"] = "clear"

            persons.append(person)

        # Global topic
        global_payload = {
            "timestamp": timestamp,
            "person_count": len(persons),
            "persons": persons,
        }
        await self._publisher.publish("office/tracking/persons", global_payload)

        # Per-zone topics
        zone_persons: dict[str, list] = {}
        for p in persons:
            zone = p["zone"]
            if zone:
                zone_persons.setdefault(zone, []).append(p)

        for zone_id, z_persons in zone_persons.items():
            zone_payload = {
                "zone": zone_id,
                "timestamp": timestamp,
                "person_count": len(z_persons),
                "persons": z_persons,
            }
            await self._publisher.publish(
                f"office/{zone_id}/tracking", zone_payload
            )

    def stop(self):
        self._running = False
