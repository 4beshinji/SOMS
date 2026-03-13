"""
WiFi Tracking Bridge — subscribes to WiFi pose data via MQTT and feeds
TrackedPerson instances into CrossCameraTracker for cross-modal fusion.

WiFi CSI nodes produce coarse floor-plane positions without visual features.
The bridge creates TrackedPerson objects with zero-vector ReID embeddings
and source_type="wifi", allowing the tracker to associate them with camera
detections using spatial+temporal cues only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import TYPE_CHECKING

import numpy as np
import paho.mqtt.client as mqtt

if TYPE_CHECKING:
    from tracking.cross_camera_tracker import CrossCameraTracker

from tracking.tracklet import TrackedPerson

logger = logging.getLogger(__name__)

# Topic pattern: office/{zone}/wifi-pose/{node_id}
_TOPIC_PATTERN = "office/+/wifi-pose/+"


class WifiTrackingBridge:
    """Bridges WiFi CSI pose estimates into the cross-camera tracker."""

    def __init__(
        self,
        cross_tracker: CrossCameraTracker,
        broker: str = "localhost",
        port: int = 1883,
    ):
        self._tracker = cross_tracker
        self._broker = broker
        self._port = port
        self._running = True
        self._client: mqtt.Client | None = None

    async def run(self):
        """Main loop: connect to MQTT and process WiFi pose messages."""
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        mqtt_user = os.getenv("MQTT_USER")
        mqtt_pass = os.getenv("MQTT_PASS")
        if mqtt_user:
            self._client.username_pw_set(mqtt_user, mqtt_pass)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        self._client.connect(self._broker, self._port)
        self._client.loop_start()

        logger.info(
            "WifiTrackingBridge started (broker=%s:%d)", self._broker, self._port
        )

        while self._running:
            await asyncio.sleep(1.0)

        self._client.loop_stop()
        self._client.disconnect()

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe(_TOPIC_PATTERN)
            logger.info("Subscribed to %s", _TOPIC_PATTERN)
        else:
            logger.error("MQTT connect failed: rc=%d", rc)

    def _on_message(self, client, userdata, msg):
        try:
            self._handle_message(msg)
        except Exception as e:
            logger.error("WiFi pose message error: %s", e, exc_info=True)

    def _handle_message(self, msg):
        """Parse WiFi pose MQTT message and feed into tracker."""
        # Topic: office/{zone}/wifi-pose/{node_id}
        parts = msg.topic.split("/")
        if len(parts) < 4:
            return

        zone = parts[1]
        node_id = parts[3]

        payload = json.loads(msg.payload)

        # Expected payload: {"persons": [{"id": int, "x": float, "y": float, "confidence": float}]}
        persons_data = payload.get("persons", [])
        if not persons_data:
            return

        now = time.time()
        persons = []

        for p in persons_data:
            person = TrackedPerson(
                track_id=int(p["id"]),
                camera_id=node_id,
                bbox_px=[0.0, 0.0, 0.0, 0.0],
                foot_px=[0.0, 0.0],
                foot_floor=[float(p["x"]), float(p["y"])],
                confidence=float(p.get("confidence", 0.5)),
                reid_embedding=np.zeros(512, dtype=np.float32),
                timestamp=payload.get("timestamp", now),
                source_type="wifi",
            )
            persons.append(person)

        self._tracker.update_camera(node_id, persons)

    def stop(self):
        self._running = False
