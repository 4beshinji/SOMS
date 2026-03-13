"""
Vision/Perception Service
MQTT-based multi-task monitoring system with YOLOv11
"""
import asyncio
import json
import logging
import time
import yaml
import os
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import components
from scheduler import TaskScheduler
from monitors import OccupancyMonitor, WhiteboardMonitor, ActivityMonitor
from image_requester import ImageRequester
from yolo_inference import YOLOInference
from pose_estimator import PoseEstimator
from state_publisher import StatePublisher
from camera_discovery import CameraDiscovery
from image_sources import ImageSourceFactory


async def main():
    logger.info("=== Vision Service Starting ===")

    # Load configuration
    config_path = Path(__file__).parent.parent / "config" / "monitors.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Initialize shared components (env vars override YAML config for Docker)
    mqtt_config = config.get("mqtt", {})
    broker = os.environ.get("MQTT_BROKER", mqtt_config.get("broker", "localhost"))
    port = int(os.environ.get("MQTT_PORT", mqtt_config.get("port", 1883)))

    logger.info(f"MQTT Broker: {broker}:{port}")

    # Initialize singletons
    ImageRequester.get_instance(broker, port)
    publisher = StatePublisher.get_instance(broker, port)

    # Load YOLO models
    yolo_config = config.get("yolo", {})
    model_path = yolo_config.get("model", "yolo11s.pt")
    pose_model_path = yolo_config.get("pose_model", "yolo11s-pose.pt")
    YOLOInference.get_instance(model_path)
    PoseEstimator.get_instance(pose_model_path)

    # Create scheduler
    scheduler = TaskScheduler()

    # Load fall detection config
    fall_detection_config = config.get("fall_detection", {})

    # Collect static camera IDs to avoid duplicates from discovery
    static_camera_ids = set()

    # Register static monitors from YAML
    for monitor_config in config.get("monitors", []):
        if not monitor_config.get("enabled", True):
            logger.info(f"Skipping disabled monitor: {monitor_config['name']}")
            continue

        monitor_type = monitor_config["type"]
        camera_id = monitor_config["camera_id"]
        zone_name = monitor_config.get("zone_name", "default")

        if monitor_type == "OccupancyMonitor":
            monitor = OccupancyMonitor(camera_id, zone_name)
        elif monitor_type == "WhiteboardMonitor":
            monitor = WhiteboardMonitor(camera_id, zone_name)
        elif monitor_type == "ActivityMonitor":
            monitor = ActivityMonitor(
                camera_id, zone_name,
                fall_detection_config=fall_detection_config,
            )
        else:
            logger.warning(f"Unknown monitor type: {monitor_type}")
            continue

        scheduler.register_monitor(monitor_config["name"], monitor)
        static_camera_ids.add(camera_id)

    # --- Camera Auto-Discovery ---
    discovery_config = config.get("discovery", {})
    if discovery_config.get("enabled", False):
        logger.info("=== Camera Discovery Starting ===")
        discovery = CameraDiscovery(
            network=discovery_config.get("network", "192.168.128.0/24"),
            timeout=discovery_config.get("timeout", 3.0),
            verify_yolo=discovery_config.get("verify_yolo", True),
            exclude_ips=discovery_config.get("exclude_ips", []),
            zone_map=discovery_config.get("zone_map", {}),
        )

        cameras = await discovery.discover()
        default_interval = discovery_config.get("default_interval_sec", 10.0)

        discovery_results = []
        for cam in cameras:
            # Skip if static config already covers this camera
            if cam.camera_id in static_camera_ids:
                logger.info(f"[Discovery] Skipping {cam.camera_id} (static config exists)")
                continue

            source = ImageSourceFactory.create(cam)
            monitor = ActivityMonitor(
                camera_id=cam.camera_id,
                zone_name=cam.zone_name or cam.camera_id,
                image_source=source,
                fall_detection_config=fall_detection_config,
            )
            monitor.interval_sec = default_interval
            monitor_name = f"discovery_{cam.camera_id}"
            scheduler.register_monitor(monitor_name, monitor)

            discovery_results.append({
                "camera_id": cam.camera_id,
                "protocol": cam.protocol,
                "address": cam.address,
                "zone_name": cam.zone_name,
                "verified": cam.verified,
            })

        # Publish discovery results via MQTT
        await publisher.publish("office/perception/discovery", {
            "cameras": discovery_results,
            "total": len(discovery_results),
            "timestamp": time.time(),
        })
        logger.info(f"=== Discovery Complete: {len(discovery_results)} cameras added ===")

    # --- Tracking Pipeline ---
    tracking_config = config.get("tracking", {})
    if tracking_config.get("enabled", False):
        logger.info("=== Tracking Pipeline Starting ===")

        # Load spatial config (ArUco markers + zone polygons)
        spatial_path = Path(__file__).parent.parent.parent.parent / "config" / "spatial.yaml"
        spatial_config = {}
        zone_polygons = {}
        aruco_markers = {}
        cameras_config = {}

        if spatial_path.exists():
            with open(spatial_path) as f:
                spatial_config = yaml.safe_load(f) or {}
            aruco_markers = spatial_config.get("aruco_markers", {})
            cameras_config = spatial_config.get("cameras", {})
            for zone_id, zone_data in spatial_config.get("zones", {}).items():
                polygon = zone_data.get("polygon", [])
                if polygon:
                    zone_polygons[zone_id] = polygon
            logger.info(
                "Spatial config: %d ArUco markers, %d zones, %d cameras",
                len(aruco_markers), len(zone_polygons), len(cameras_config),
            )
        else:
            logger.warning("No spatial.yaml found at %s", spatial_path)

        # Initialize ArUco calibrator
        from tracking.aruco_calibrator import ArucoCalibrator

        calib_config = tracking_config.get("calibration", {})
        calibrator = ArucoCalibrator.get_instance(
            aruco_markers=aruco_markers,
            aruco_dict_name=calib_config.get("aruco_dict", "DICT_4X4_50"),
            cache_path=calib_config.get("cache_path"),
        )

        # Initialize ReID embedder
        from tracking.reid_embedder import ReIDEmbedder

        reid_model = tracking_config.get("reid_model", "osnet_x0_5")
        ReIDEmbedder.get_instance(reid_model)

        # Create cross-camera tracker
        from tracking.cross_camera_tracker import CrossCameraTracker

        assoc = tracking_config.get("association", {})
        cross_tracker = CrossCameraTracker(
            zone_polygons=zone_polygons,
            reid_weight=assoc.get("reid_weight", 0.5),
            spatial_weight=assoc.get("spatial_weight", 0.3),
            temporal_weight=assoc.get("temporal_weight", 0.2),
            match_threshold=assoc.get("match_threshold", 0.5),
            spatial_gate_m=assoc.get("spatial_gate_m", 5.0),
            temporal_gate_s=assoc.get("temporal_gate_s", 30.0),
            tracklet_timeout_s=assoc.get("tracklet_timeout_s", 60.0),
            global_track_timeout_s=assoc.get("global_track_timeout_s", 300.0),
        )

        # Create per-camera TrackingMonitors
        from monitors.tracking import TrackingMonitor

        tracker_cfg_name = tracking_config.get("tracker", "botsort.yaml")
        tracker_cfg_path = str(
            Path(__file__).parent.parent / "config" / "tracker" / tracker_cfg_name
        )

        tracking_cameras = tracking_config.get("cameras", [])
        for cam_cfg in tracking_cameras:
            cam_id = cam_cfg["camera_id"]
            zone = cam_cfg["zone_name"]

            # Create image source for this camera if it was discovered
            source = None
            for name, monitor in scheduler.monitors.items():
                if hasattr(monitor, 'camera_id') and monitor.camera_id == cam_id:
                    source = monitor._image_source
                    break

            track_monitor = TrackingMonitor(
                camera_id=cam_id,
                zone_name=zone,
                cross_camera_tracker=cross_tracker,
                model_path=yolo_config.get("model", "yolo11s.pt"),
                tracker_config=tracker_cfg_path,
                image_source=source,
            )
            scheduler.register_monitor(f"tracking_{cam_id}", track_monitor)

        # Auto-calibrate cameras
        if calib_config.get("auto_calibrate", True):
            # Collect image sources from tracking monitors
            track_sources = {}
            for name, monitor in scheduler.monitors.items():
                if name.startswith("tracking_") and monitor._image_source is not None:
                    track_sources[monitor.camera_id] = monitor._image_source

            if track_sources:
                min_markers = calib_config.get("min_markers", 4)
                results = await calibrator.calibrate_all(
                    cameras_config, track_sources, min_markers
                )
                for r in results:
                    status = r.get("status", "unknown")
                    cam = r.get("camera_id", "?")
                    await publisher.publish("office/perception/calibration", r)
                    logger.info("Calibration %s: %s", cam, status)

        # Create and register MTMC publisher
        from tracking.mtmc_publisher import MTMCPublisher

        mtmc_publisher = MTMCPublisher(
            tracker=cross_tracker,
            publish_interval_sec=tracking_config.get("publish_interval_sec", 0.5),
        )
        scheduler.register_service("mtmc_publisher", mtmc_publisher)

        logger.info("=== Tracking Pipeline Ready ===")

    # --- VLM Analysis Pipeline ---
    vlm_config = config.get("vlm", {})
    if vlm_config.get("enabled", False):
        logger.info("=== VLM Pipeline Starting ===")

        from vlm.vlm_client import VLMClient
        from vlm.vlm_analyzer import VLMAnalyzer
        from vlm.periodic_service import VLMPeriodicService

        vlm_api_url = os.environ.get("VLM_API_URL", vlm_config.get("api_url", "http://localhost:11434"))
        vlm_model = os.environ.get("VLM_MODEL", vlm_config.get("model", "qwen3-vl:8b"))
        vlm_api_style = vlm_config.get("api_style", "ollama")
        vlm_timeout = vlm_config.get("timeout_sec", 30)

        vlm_client = VLMClient(
            api_url=vlm_api_url,
            model=vlm_model,
            timeout_sec=vlm_timeout,
            api_style=vlm_api_style,
        )
        vlm_analyzer = VLMAnalyzer(
            vlm_client=vlm_client,
            publisher=publisher,
            cooldowns=vlm_config.get("cooldowns"),
        )

        # Inject VLM analyzer into existing ActivityMonitors
        for name, monitor in scheduler.monitors.items():
            if isinstance(monitor, ActivityMonitor):
                monitor._vlm_analyzer = vlm_analyzer
                logger.info("VLM analyzer injected into %s", name)

        # Periodic service
        periodic_cfg = vlm_config.get("periodic", {})
        if periodic_cfg.get("enabled", True):
            zone_sources = {}
            for name, monitor in scheduler.monitors.items():
                if hasattr(monitor, 'zone_name') and hasattr(monitor, '_image_source') and monitor._image_source:
                    zone_sources.setdefault(monitor.zone_name, monitor._image_source)
            if zone_sources:
                periodic = VLMPeriodicService(
                    vlm_analyzer,
                    zone_sources,
                    interval_sec=periodic_cfg.get("interval_sec", 300),
                )
                scheduler.register_service("vlm_periodic", periodic)
                logger.info("VLM periodic service registered with %d zones", len(zone_sources))

        logger.info("=== VLM Pipeline Ready (model=%s, api=%s) ===", vlm_model, vlm_api_style)

    logger.info("=== Vision Service Ready ===")

    # Start monitoring
    await scheduler.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
