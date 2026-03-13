"""
CalibrationManager — orchestrates 2-step remote HX711 calibration.

Step 1 (tare): User empties the shelf → Brain sends MCP tare command
Step 2 (set_known_weight): User places known weight → Brain sends MCP calibrate command

Tracks calibration state per device to enforce correct step ordering.
"""
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Calibration session expires after 10 minutes
CALIBRATION_TIMEOUT_SEC = 600


@dataclass
class CalibrationSession:
    """In-progress calibration for a single device."""
    device_id: str
    step: str           # "awaiting_tare" | "awaiting_known_weight" | "complete"
    started_at: float
    tare_result: Optional[dict] = None
    calibrate_result: Optional[dict] = None


class CalibrationManager:
    """Manages calibration sessions for shelf sensors."""

    def __init__(self):
        self._sessions: Dict[str, CalibrationSession] = {}

    def _cleanup_expired(self):
        now = time.time()
        expired = [
            k for k, s in self._sessions.items()
            if now - s.started_at > CALIBRATION_TIMEOUT_SEC
        ]
        for k in expired:
            del self._sessions[k]
            logger.info("Calibration session expired: %s", k)

    def start_or_get(self, device_id: str) -> CalibrationSession:
        """Start a new calibration session or return existing one."""
        self._cleanup_expired()
        if device_id not in self._sessions:
            self._sessions[device_id] = CalibrationSession(
                device_id=device_id,
                step="awaiting_tare",
                started_at=time.time(),
            )
            logger.info("Calibration session started: %s", device_id)
        return self._sessions[device_id]

    def get_session(self, device_id: str) -> Optional[CalibrationSession]:
        self._cleanup_expired()
        return self._sessions.get(device_id)

    def record_tare_done(self, device_id: str, result: dict):
        session = self._sessions.get(device_id)
        if session:
            session.step = "awaiting_known_weight"
            session.tare_result = result
            logger.info("Tare complete for %s: %s", device_id, result)

    def record_calibrate_done(self, device_id: str, result: dict):
        session = self._sessions.get(device_id)
        if session:
            session.step = "complete"
            session.calibrate_result = result
            logger.info("Calibration complete for %s: %s", device_id, result)

    def finish(self, device_id: str):
        """Remove completed session."""
        self._sessions.pop(device_id, None)

    def validate_step(self, device_id: str, step: str) -> tuple[bool, str]:
        """Validate that the requested step is valid for current state.

        Returns (is_valid, reason).
        """
        if step == "tare":
            # tare is always valid — starts or restarts a session
            return True, "OK"
        elif step == "set_known_weight":
            session = self.get_session(device_id)
            if session is None:
                return False, "キャリブレーション未開始。先に step=tare を実行してください"
            if session.step != "awaiting_known_weight":
                return False, f"不正なステップ順序: 現在のステップは '{session.step}'"
            return True, "OK"
        else:
            return False, f"不明なステップ: {step}. 有効値: tare, set_known_weight"
