"""
WiFi CSI Pose Service — processes raw CSI data from ESP32-S3 nodes,
runs pose estimation (CNN or mock), applies YOLO cross-modal calibration,
and publishes corrected floor positions via MQTT.
"""
import asyncio
import json
import logging
import os
import time

import numpy as np
import paho.mqtt.client as mqtt

from config import load_config
from csi_processor import CSIProcessor, CSIFrame
from pose_estimator import WifiPoseEstimator
from wifi_calibrator import WifiCalibrator
from calibration_bridge import CalibrationBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class WifiPoseService:
    """Main service: CSI → pose estimation → calibration → MQTT publish."""

    def __init__(self, config: dict):
        self._config = config
        mqtt_cfg = config.get("mqtt", {})
        self._broker = mqtt_cfg.get("broker", "localhost")
        self._port = mqtt_cfg.get("port", 1883)

        # CSI processor
        csi_cfg = config.get("csi", {})
        self._csi = CSIProcessor(
            subcarrier_count=csi_cfg.get("subcarrier_count", 52),
            hampel_window=csi_cfg.get("hampel_window", 5),
            hampel_threshold=csi_cfg.get("hampel_threshold", 3.0),
            spectrogram_window_sec=csi_cfg.get("spectrogram_window_sec", 1.0),
        )

        # Pose estimator
        model_cfg = config.get("model", {})
        self._estimator = WifiPoseEstimator(
            model_type=model_cfg.get("type", "mock"),
            model_path=model_cfg.get("path"),
        )

        # Calibrator
        calib_cfg = config.get("calibration", {})
        self._calibrator = WifiCalibrator.get_instance(
            cache_path=calib_cfg.get("cache_path"),
            sliding_window_size=calib_cfg.get("sliding_window_size", 200),
            min_pairs=calib_cfg.get("min_pairs", 20),
        )

        # Calibration bridge (YOLO ↔ WiFi matching)
        self._calib_bridge: CalibrationBridge | None = None
        if calib_cfg.get("enabled", True):
            self._calib_bridge = CalibrationBridge(
                calibrator=self._calibrator,
                broker=self._broker,
                port=self._port,
                match_distance_m=calib_cfg.get("yolo_match_distance_m", 3.0),
                match_time_s=calib_cfg.get("yolo_match_time_s", 2.0),
            )

        # Node zone mapping
        self._node_zones: dict[str, str] = {}
        for node_id, node_cfg in config.get("nodes", {}).items():
            self._node_zones[node_id] = node_cfg.get("zone", "")

        self._client: mqtt.Client | None = None
        self._running = True

    def start(self):
        """Connect to MQTT and start processing."""
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        mqtt_user = os.getenv("MQTT_USER")
        mqtt_pass = os.getenv("MQTT_PASS")
        if mqtt_user:
            self._client.username_pw_set(mqtt_user, mqtt_pass)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        self._client.connect(self._broker, self._port)
        self._client.loop_start()

        if self._calib_bridge:
            self._calib_bridge.start()

        logger.info("WifiPoseService started (broker=%s:%d)", self._broker, self._port)

    def stop(self):
        self._running = False
        if self._calib_bridge:
            self._calib_bridge.stop()
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe("office/+/wifi-csi/+")
            logger.info("Subscribed to office/+/wifi-csi/+")
        else:
            logger.error("MQTT connect failed: rc=%d", rc)

    def _on_message(self, client, userdata, msg):
        try:
            self._process_csi(msg)
        except Exception as e:
            logger.error("CSI processing error: %s", e, exc_info=True)

    def _process_csi(self, msg):
        """Full pipeline: CSI → spectrogram → pose → calibrate → publish."""
        parts = msg.topic.split("/")
        if len(parts) < 4:
            return

        zone = parts[1]
        node_id = parts[3]
        payload = json.loads(msg.payload)

        amplitudes = np.array(payload.get("amplitudes", []), dtype=np.float64)
        if amplitudes.size == 0:
            return

        timestamp = payload.get("timestamp", time.time())

        # CSI preprocessing → spectrogram
        frame = CSIFrame(
            node_id=node_id,
            timestamp=timestamp,
            amplitudes=amplitudes,
            zone=zone,
        )
        spectrogram = self._csi.add_frame(frame)
        if spectrogram is None:
            return  # Window not yet full

        # Pose estimation
        estimates = self._estimator.predict(spectrogram, zone)
        if not estimates:
            return

        # Calibration + publish
        persons = []
        for est in estimates:
            raw_xy = [est.x, est.y]
            corrected_xy = self._calibrator.correct(zone, raw_xy)

            persons.append({
                "id": est.person_id,
                "x": corrected_xy[0],
                "y": corrected_xy[1],
                "confidence": est.confidence,
            })

            # Also publish raw for calibration bridge
            if self._calib_bridge:
                raw_payload = json.dumps({
                    "persons": [{"id": est.person_id, "x": raw_xy[0], "y": raw_xy[1]}],
                    "timestamp": timestamp,
                })
                self._client.publish(
                    f"office/{zone}/wifi-pose-raw/{node_id}", raw_payload
                )

        # Publish corrected positions
        pose_payload = json.dumps({
            "node_id": node_id,
            "zone": zone,
            "timestamp": timestamp,
            "persons": persons,
        })
        self._client.publish(f"office/{zone}/wifi-pose/{node_id}", pose_payload)


async def main():
    logger.info("=== WiFi Pose Service Starting ===")

    config = load_config()
    service = WifiPoseService(config)
    service.start()

    logger.info("=== WiFi Pose Service Ready ===")

    try:
        while True:
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        pass
    finally:
        service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
