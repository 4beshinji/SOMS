"""
V4L2Source — USB webcam capture via cv2.VideoCapture.

Address formats:
  - "0", "1", ...     → device index passed to cv2.VideoCapture(int)
  - "/dev/video0"     → device path passed to cv2.VideoCapture(str)
  - "v4l2:///dev/video0" → same as above (scheme stripped)

Optional query params on address (path form): ?w=640&h=480&fps=15
"""
import asyncio
import logging
import time
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

import cv2
import numpy as np

from image_sources.base import CameraInfo, ImageSource

logger = logging.getLogger(__name__)


def _parse_address(address: str) -> Tuple[object, dict]:
    """Return (device, params). device is int (index) or str (path)."""
    params: dict = {}
    if "?" in address:
        addr, query = address.split("?", 1)
        params = {k: v[0] for k, v in parse_qs(query).items()}
    else:
        addr = address

    if addr.startswith("v4l2://"):
        addr = addr[len("v4l2://"):]

    if addr.isdigit():
        return int(addr), params
    return addr, params


class V4L2Source(ImageSource):
    """Captures frames from a Video4Linux2 device (USB webcam)."""

    def __init__(self, camera_info: CameraInfo):
        super().__init__(camera_info)
        self._cap: Optional[cv2.VideoCapture] = None
        self._device, self._params = _parse_address(camera_info.address)

    def _open(self) -> bool:
        if self._cap is not None and self._cap.isOpened():
            return True
        # cv2.CAP_V4L2 backend gives more predictable behavior on Linux
        backend = getattr(cv2, "CAP_V4L2", 0)
        try:
            self._cap = cv2.VideoCapture(self._device, backend)
        except Exception as e:
            logger.warning(f"[V4L2] Open failed for {self._device}: {e}")
            self._cap = None
            return False
        if not self._cap.isOpened():
            logger.warning(f"[V4L2] Device not opened: {self._device}")
            self._cap = None
            return False

        if "w" in self._params:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self._params["w"]))
        if "h" in self._params:
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self._params["h"]))
        if "fps" in self._params:
            self._cap.set(cv2.CAP_PROP_FPS, float(self._params["fps"]))
        # Keep latency low — webcams default to large internal buffers.
        try:
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return True

    async def capture(self) -> Optional[np.ndarray]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._capture_sync)

    def _capture_sync(self) -> Optional[np.ndarray]:
        if not self._open():
            return None
        # Drain stale frame so we get the latest one.
        self._cap.grab()
        ret, frame = self._cap.read()
        if not ret or frame is None:
            logger.warning(
                f"[V4L2] Read failed for {self.camera_info.camera_id}, reopening"
            )
            self._release()
            return None
        self.camera_info.last_seen = time.time()
        return frame

    async def health_check(self) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._health_sync)

    def _health_sync(self) -> bool:
        if not self._open():
            return False
        ret, _ = self._cap.read()
        return ret

    def _release(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    async def close(self):
        self._release()
