"""
Snapshot HTTP Server — lightweight aiohttp service that serves camera
metadata and on-demand JPEG snapshots for the admin dashboard.

Runs on port 8009 (configurable via SNAPSHOT_PORT env var) alongside the
main perception monitor loop.  Camera URLs are resolved from the discovery
zone_map in monitors.yaml and the cameras section of spatial.yaml.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from aiohttp import web

logger = logging.getLogger(__name__)

# Max threads for blocking cv2 captures
_POOL = ThreadPoolExecutor(max_workers=4)

# Candidate snapshot URL patterns (same order as camera_discovery.py)
_URL_PATTERNS: list[str] = [
    "http://{ip}:81/",
    "http://{ip}:81/stream",
    "http://{ip}/stream",
    "http://{ip}:8080/?action=stream",
]


def _ip_from_camera_id(camera_id: str) -> str | None:
    """Extract IP address from camera_id like 'cam_192_168_128_172'."""
    parts = camera_id.replace("cam_", "").split("_")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return ".".join(parts)
    return None


def _grab_frame_cv2(url: str, timeout_ms: int = 10000) -> bytes | None:
    """Blocking: open stream via cv2, grab one frame, return JPEG bytes."""
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    try:
        if not cap.isOpened():
            return None
        ret, frame = cap.read()
        if not ret or frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else None
    finally:
        cap.release()


def _grab_frame_mjpeg(url: str, timeout_sec: float = 8.0) -> bytes | None:
    """Grab one JPEG frame from an MJPEG multipart HTTP stream."""
    import urllib.request

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            buf = b""
            jpeg_start = -1
            while len(buf) < 500_000:  # Safety limit ~500KB
                chunk = resp.read(4096)
                if not chunk:
                    break
                buf += chunk
                if jpeg_start < 0:
                    jpeg_start = buf.find(b"\xff\xd8")
                if jpeg_start >= 0:
                    jpeg_end = buf.find(b"\xff\xd9", jpeg_start + 2)
                    if jpeg_end >= 0:
                        return buf[jpeg_start : jpeg_end + 2]
    except Exception:
        return None
    return None


def _grab_frame(url: str) -> bytes | None:
    """Grab one frame — try fast MJPEG parse first, fall back to cv2."""
    if "81" in url or "stream" in url or "mjpg" in url:
        result = _grab_frame_mjpeg(url)
        if result:
            return result
    return _grab_frame_cv2(url)


class SnapshotServer:
    """Serves camera list and JPEG snapshots over HTTP."""

    # Class-level frame caches — written by monitors, read by HTTP handler
    _frame_cache: dict[str, tuple[float, bytes]] = {}
    _annotated_cache: dict[str, tuple[float, bytes]] = {}
    # Persistent cache — never expires, used when camera goes offline
    _last_good_cache: dict[str, tuple[float, bytes]] = {}

    @classmethod
    def cache_frame(cls, camera_id: str, frame: np.ndarray):
        """Called by monitors to cache the latest frame as JPEG."""
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            entry = (time.time(), buf.tobytes())
            cls._frame_cache[camera_id] = entry
            cls._last_good_cache[camera_id] = entry

    @classmethod
    def cache_annotated(cls, camera_id: str, frame: np.ndarray, detections: list):
        """Cache frame with YOLO bbox overlay drawn on it."""
        annotated = frame.copy()
        for det in detections:
            bbox = det.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            cls_name = det.get("class", "?")
            conf = det.get("confidence", 0)
            color = (0, 255, 0) if cls_name == "person" else (0, 255, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f"{cls_name} {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
            cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            cls._annotated_cache[camera_id] = (time.time(), buf.tobytes())

    def __init__(self, port: int = 8019):
        self._port = port
        # camera_id -> {zone, ip, urls: [str], position: [x,y], ...}
        self._cameras: dict[str, dict[str, Any]] = {}
        self._cache_ttl = 30.0  # frames from monitors are fresh enough for 30s
        # camera_id -> verified working URL (memoised after first success)
        self._working_urls: dict[str, str] = {}
        # Discovery config — set by set_discovery_config() for on-demand scans
        self._discovery_config: dict[str, Any] | None = None
        self._discovery_running = False
        # Cross-camera tracker reference for live tracking API
        self._tracker: Any | None = None

    def set_discovery_config(self, discovery_config: dict[str, Any]):
        """Store discovery config for on-demand LAN scans."""
        self._discovery_config = discovery_config

    def set_tracker(self, tracker):
        """Store reference to CrossCameraTracker for live tracking API."""
        self._tracker = tracker

    def set_discovered_url(self, camera_id: str, url: str, zone: str = ""):
        """Register a verified working URL from camera discovery."""
        if camera_id not in self._cameras:
            ip = _ip_from_camera_id(camera_id)
            self._cameras[camera_id] = {
                "zone": zone,
                "ip": ip,
                "position": None,
                "fov_deg": None,
                "orientation_deg": None,
                "resolution": None,
                "urls": [url],
            }
        else:
            urls = self._cameras[camera_id].get("urls", [])
            if url not in urls:
                urls.insert(0, url)
                self._cameras[camera_id]["urls"] = urls
        self._working_urls[camera_id] = url
        logger.info("Set discovered URL for %s: %s", camera_id, url)

    def load_config(
        self,
        monitors_yaml: Path | None = None,
        spatial_yaml: Path | None = None,
    ):
        """Build camera registry from config files."""
        cameras: dict[str, dict[str, Any]] = {}

        # 1) spatial.yaml cameras (have position, zone, fov)
        if spatial_yaml and spatial_yaml.exists():
            with open(spatial_yaml) as f:
                spatial = yaml.safe_load(f) or {}
            for cam_id, cam_cfg in spatial.get("cameras", {}).items():
                ip = _ip_from_camera_id(cam_id)
                cameras[cam_id] = {
                    "zone": cam_cfg.get("zone", ""),
                    "ip": ip,
                    "position": cam_cfg.get("position"),
                    "fov_deg": cam_cfg.get("fov_deg"),
                    "orientation_deg": cam_cfg.get("orientation_deg"),
                    "resolution": cam_cfg.get("resolution"),
                    "urls": [p.format(ip=ip) for p in _URL_PATTERNS] if ip else [],
                }

        # 2) monitors.yaml discovery zone_map (may add cameras not in spatial)
        if monitors_yaml and monitors_yaml.exists():
            with open(monitors_yaml) as f:
                mon_cfg = yaml.safe_load(f) or {}
            zone_map = mon_cfg.get("discovery", {}).get("zone_map", {})
            for ip, zone in zone_map.items():
                cam_id = f"cam_{ip.replace('.', '_')}"
                if cam_id not in cameras:
                    cameras[cam_id] = {
                        "zone": zone,
                        "ip": ip,
                        "position": None,
                        "fov_deg": None,
                        "orientation_deg": None,
                        "resolution": None,
                        "urls": [p.format(ip=ip) for p in _URL_PATTERNS],
                    }
                else:
                    # merge zone if missing
                    if not cameras[cam_id].get("zone"):
                        cameras[cam_id]["zone"] = zone

            # Static monitors (e.g. ESP32-CAM MCP camera)
            for monitor in mon_cfg.get("monitors", []):
                cam_id = monitor.get("camera_id", "")
                if cam_id and cam_id not in cameras:
                    cameras[cam_id] = {
                        "zone": monitor.get("zone_name", ""),
                        "ip": None,
                        "position": None,
                        "fov_deg": None,
                        "orientation_deg": None,
                        "resolution": None,
                        "urls": [],  # MCP cameras don't have HTTP URLs
                    }

        self._cameras = cameras
        logger.info("SnapshotServer: %d cameras loaded", len(cameras))

    # ── HTTP Handlers ─────────────────────────────────────────────

    async def handle_list(self, request: web.Request) -> web.Response:
        """GET /cameras — list all cameras with metadata."""
        result = []
        for cam_id, info in self._cameras.items():
            result.append({
                "camera_id": cam_id,
                "zone": info.get("zone", ""),
                "position": info.get("position"),
                "fov_deg": info.get("fov_deg"),
                "orientation_deg": info.get("orientation_deg"),
                "resolution": info.get("resolution"),
                "has_stream": bool(info.get("urls")),
            })
        return web.json_response(result)

    async def handle_snapshot(self, request: web.Request) -> web.Response:
        """GET /cameras/{camera_id}/snapshot — return JPEG snapshot."""
        camera_id = request.match_info["camera_id"]
        info = self._cameras.get(camera_id)
        if not info:
            raise web.HTTPNotFound(text=f"Camera {camera_id} not found")

        # 1) Check monitor frame cache (populated by running monitors)
        want_overlay = request.query.get("overlay") == "1"
        # Try annotated first, fall back to plain frame
        cached = None
        if want_overlay:
            cached = self._annotated_cache.get(camera_id)
        if not cached or time.time() - cached[0] >= self._cache_ttl:
            cached = self._frame_cache.get(camera_id)
        if cached and time.time() - cached[0] < self._cache_ttl:
            return web.Response(
                body=cached[1],
                content_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=5"},
            )

        # 2) Fallback: on-demand grab (slow, only when monitor isn't running)
        urls = info.get("urls", [])
        jpeg_bytes = None
        if urls:
            loop = asyncio.get_event_loop()
            ordered = []
            working = self._working_urls.get(camera_id)
            if working:
                ordered.append(working)
            ordered.extend(u for u in urls if u != working)

            for url in ordered:
                jpeg_bytes = await loop.run_in_executor(_POOL, _grab_frame, url)
                if jpeg_bytes:
                    self._working_urls[camera_id] = url
                    break

        if jpeg_bytes:
            entry = (time.time(), jpeg_bytes)
            self._frame_cache[camera_id] = entry
            self._last_good_cache[camera_id] = entry
            return web.Response(
                body=jpeg_bytes,
                content_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=5"},
            )

        # 3) Last known good frame (stale but better than nothing)
        last_good = self._last_good_cache.get(camera_id)
        if last_good:
            return web.Response(
                body=last_good[1],
                content_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=5"},
            )

        raise web.HTTPServiceUnavailable(
            text=f"No frame available for {camera_id}"
        )

    async def handle_tracking_live(self, request: web.Request) -> web.Response:
        """GET /tracking/live — return current global tracks from MTMC tracker."""
        if self._tracker is None:
            return web.json_response(
                {"persons": [], "person_count": 0, "timestamp": time.time()},
            )

        tracks = self._tracker.get_global_tracks()
        now = time.time()
        persons = []
        for t in tracks:
            # Include recent trail from tracklet detections
            trail: list[list[float]] = []
            for tracklet in t.tracklets.values():
                for det in tracklet.detections:
                    pos = det.foot_floor
                    if pos and pos != [0.0, 0.0]:
                        trail.append([round(pos[0], 2), round(pos[1], 2), round(det.timestamp, 2)])

            # Sort trail by time, deduplicate close positions
            trail.sort(key=lambda p: p[2])

            persons.append({
                "global_id": t.global_id,
                "floor_x_m": t.floor_position[0],
                "floor_y_m": t.floor_position[1],
                "zone": t.zone_id,
                "cameras": t.camera_ids,
                "confidence": max(
                    (
                        tk.detections[-1].confidence
                        for tk in t.tracklets.values()
                        if tk.detections
                    ),
                    default=0.0,
                ),
                "duration_sec": round(t.duration_sec, 1),
                "trail": trail[-30:],  # Last 30 position samples
            })

        return web.json_response({
            "persons": persons,
            "person_count": len(persons),
            "timestamp": now,
        })

    async def handle_discover(self, request: web.Request) -> web.Response:
        """POST /cameras/discover — trigger LAN camera scan and return results."""
        if self._discovery_running:
            return web.json_response(
                {"error": "Discovery already in progress"},
                status=409,
            )
        if not self._discovery_config:
            return web.json_response(
                {"error": "Discovery not configured"},
                status=501,
            )

        self._discovery_running = True
        try:
            from camera_discovery import CameraDiscovery

            cfg = self._discovery_config
            scan_range_cfg = cfg.get("scan_range")
            scan_range = tuple(scan_range_cfg) if scan_range_cfg else None
            discovery = CameraDiscovery(
                network=cfg.get("network", "192.168.128.0/24"),
                timeout=cfg.get("timeout", 3.0),
                verify_yolo=cfg.get("verify_yolo", False),
                exclude_ips=cfg.get("exclude_ips", []),
                zone_map=cfg.get("zone_map", {}),
                scan_range=scan_range,
            )
            cameras = await discovery.discover()

            results = []
            for cam in cameras:
                # Register discovered URL in snapshot server
                self.set_discovered_url(cam.camera_id, cam.address, cam.zone_name)
                results.append({
                    "camera_id": cam.camera_id,
                    "address": cam.address,
                    "zone": cam.zone_name,
                    "verified": cam.verified,
                })

            logger.info("On-demand discovery found %d cameras", len(results))
            return web.json_response({
                "cameras": results,
                "total": len(results),
                "timestamp": time.time(),
            })
        except Exception as e:
            logger.exception("Discovery failed")
            return web.json_response(
                {"error": str(e)},
                status=500,
            )
        finally:
            self._discovery_running = False

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self):
        """Start the HTTP server (non-blocking)."""
        app = web.Application()
        app.router.add_get("/cameras", self.handle_list)
        app.router.add_post("/cameras/discover", self.handle_discover)
        app.router.add_get("/cameras/{camera_id}/snapshot", self.handle_snapshot)
        app.router.add_get("/tracking/live", self.handle_tracking_live)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("SnapshotServer listening on :%d", self._port)
