"""
Calibration Bridge — subscribes to YOLO tracking results and matches them
with WiFi pose estimates to generate CalibrationPairs.

Uses spatial+temporal proximity to associate YOLO floor positions with
WiFi estimates from the same zone within a configurable time window.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass

import paho.mqtt.client as mqtt

from wifi_calibrator import CalibrationPair, WifiCalibrator

logger = logging.getLogger(__name__)


@dataclass
class _PoseRecord:
    """Internal record for temporal matching."""
    x: float
    y: float
    zone: str
    timestamp: float
    source: str  # "wifi" or "yolo"
    node_id: str = ""


class CalibrationBridge:
    """Matches YOLO and WiFi observations to produce CalibrationPairs."""

    def __init__(
        self,
        calibrator: WifiCalibrator,
        broker: str = "localhost",
        port: int = 1883,
        match_distance_m: float = 3.0,
        match_time_s: float = 2.0,
        buffer_size: int = 100,
    ):
        self._calibrator = calibrator
        self._broker = broker
        self._port = port
        self._match_dist = match_distance_m
        self._match_time = match_time_s

        # Buffers for temporal matching
        self._wifi_buffer: deque[_PoseRecord] = deque(maxlen=buffer_size)
        self._yolo_buffer: deque[_PoseRecord] = deque(maxlen=buffer_size)

        self._client: mqtt.Client | None = None

    def start(self):
        """Connect to MQTT and subscribe to relevant topics."""
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        mqtt_user = os.getenv("MQTT_USER")
        mqtt_pass = os.getenv("MQTT_PASS")
        if mqtt_user:
            self._client.username_pw_set(mqtt_user, mqtt_pass)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        self._client.connect(self._broker, self._port)
        self._client.loop_start()

        logger.info("CalibrationBridge started (broker=%s:%d)", self._broker, self._port)

    def stop(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            # Subscribe to YOLO tracking output
            client.subscribe("office/tracking/persons")
            # Subscribe to raw WiFi pose estimates (pre-calibration)
            client.subscribe("office/+/wifi-pose-raw/+")
            logger.info("CalibrationBridge subscribed to tracking + wifi-pose-raw")
        else:
            logger.error("CalibrationBridge MQTT connect failed: rc=%d", rc)

    def _on_message(self, client, userdata, msg):
        try:
            if msg.topic == "office/tracking/persons":
                self._handle_yolo(msg)
            elif "/wifi-pose-raw/" in msg.topic:
                self._handle_wifi_raw(msg)
        except Exception as e:
            logger.error("CalibrationBridge message error: %s", e, exc_info=True)

    def _handle_yolo(self, msg):
        """Extract YOLO person positions for calibration matching."""
        payload = json.loads(msg.payload)
        persons = payload.get("persons", [])
        ts = payload.get("timestamp", time.time())

        for p in persons:
            zone = p.get("zone", "")
            if not zone:
                continue
            # Only use camera-sourced positions (not WiFi-fed ones)
            cameras = p.get("cameras", [])
            if not cameras:
                continue

            record = _PoseRecord(
                x=p["floor_x_m"],
                y=p["floor_y_m"],
                zone=zone,
                timestamp=ts,
                source="yolo",
            )
            self._yolo_buffer.append(record)

        # Attempt matching after adding YOLO data
        self._match_and_add()

    def _handle_wifi_raw(self, msg):
        """Extract raw WiFi position estimates (before calibration)."""
        parts = msg.topic.split("/")
        if len(parts) < 4:
            return

        zone = parts[1]
        node_id = parts[3]
        payload = json.loads(msg.payload)

        for p in payload.get("persons", []):
            record = _PoseRecord(
                x=float(p["x"]),
                y=float(p["y"]),
                zone=zone,
                timestamp=payload.get("timestamp", time.time()),
                source="wifi",
                node_id=node_id,
            )
            self._wifi_buffer.append(record)

    def _match_and_add(self):
        """Match WiFi and YOLO observations by zone + proximity + time."""
        now = time.time()
        matched_wifi_indices = set()

        for yolo in self._yolo_buffer:
            if now - yolo.timestamp > self._match_time * 2:
                continue  # Too old

            for i, wifi in enumerate(self._wifi_buffer):
                if i in matched_wifi_indices:
                    continue
                if wifi.zone != yolo.zone:
                    continue
                if abs(wifi.timestamp - yolo.timestamp) > self._match_time:
                    continue

                dist = ((wifi.x - yolo.x) ** 2 + (wifi.y - yolo.y) ** 2) ** 0.5
                if dist > self._match_dist:
                    continue

                # Found a match
                pair = CalibrationPair(
                    wifi_xy=[wifi.x, wifi.y],
                    yolo_xy=[yolo.x, yolo.y],
                    timestamp=max(wifi.timestamp, yolo.timestamp),
                    zone=yolo.zone,
                    confidence=1.0 - dist / self._match_dist,
                )
                self._calibrator.add_pair(pair)
                matched_wifi_indices.add(i)
                break

        # Prune old entries
        cutoff = now - self._match_time * 3
        while self._wifi_buffer and self._wifi_buffer[0].timestamp < cutoff:
            self._wifi_buffer.popleft()
        while self._yolo_buffer and self._yolo_buffer[0].timestamp < cutoff:
            self._yolo_buffer.popleft()
