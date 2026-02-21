"""
MTMC Publisher — periodically publishes global tracking state to MQTT.

Publishes:
  - office/tracking/persons: All tracked persons across all cameras
  - office/{zone}/tracking: Per-zone person summaries
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tracking.cross_camera_tracker import CrossCameraTracker

from state_publisher import StatePublisher

logger = logging.getLogger(__name__)


class MTMCPublisher:
    """Publishes global tracking data at a fixed interval."""

    def __init__(
        self,
        tracker: CrossCameraTracker,
        publish_interval_sec: float = 0.5,
    ):
        self._tracker = tracker
        self._interval = publish_interval_sec
        self._publisher = StatePublisher.get_instance()
        self._running = True

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
            persons.append({
                "global_id": track.global_id,
                "floor_x_m": track.floor_position[0],
                "floor_y_m": track.floor_position[1],
                "zone": track.zone_id,
                "cameras": track.camera_ids,
                "confidence": max(
                    (
                        t.detections[-1].confidence
                        for t in track.tracklets.values()
                        if t.detections
                    ),
                    default=0.0,
                ),
                "duration_sec": track.duration_sec,
            })

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
