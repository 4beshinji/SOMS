"""
Sensor fusion logic for combining multiple sensor readings,
with channel-type-aware processing (analog, event, state).
"""
import math
import time
from enum import Enum
from typing import List, Tuple, Dict, Optional


# ── Channel Classification ──────────────────────────────────────────


class ChannelType(Enum):
    ANALOG = "analog"          # Continuous numeric (temperature, humidity, ...)
    EVENT = "event"            # Pulse/spike (motion, vibration)
    STATE = "state"            # Binary on/off (door, presence, contact)
    PASSTHROUGH = "passthrough"  # Unknown — store and display as-is


CHANNEL_REGISTRY: Dict[str, ChannelType] = {
    # Analog
    "temperature": ChannelType.ANALOG,
    "humidity": ChannelType.ANALOG,
    "co2": ChannelType.ANALOG,
    "pressure": ChannelType.ANALOG,
    "illuminance": ChannelType.ANALOG,
    "gas_resistance": ChannelType.ANALOG,
    "soil_moisture": ChannelType.ANALOG,
    "soil_temperature": ChannelType.ANALOG,
    # Event
    "motion": ChannelType.EVENT,
    "motion_count": ChannelType.EVENT,
    "vibration": ChannelType.EVENT,
    # State
    "door": ChannelType.STATE,
    "presence": ChannelType.STATE,
    "contact": ChannelType.STATE,
    "occupancy": ChannelType.STATE,
}


def classify_channel(channel: str) -> ChannelType:
    """Classify a channel name. Unknown channels are PASSTHROUGH."""
    return CHANNEL_REGISTRY.get(channel, ChannelType.PASSTHROUGH)


# ── Sensor Fusion (existing, extended) ──────────────────────────────


class SensorFusion:
    """Combines multiple sensor readings with reliability weighting."""

    HALF_LIFE = {
        "temperature": 120,
        "humidity": 120,
        "co2": 60,
        "illuminance": 120,
        "occupancy": 30,
        "pir": 10,
        "weight": 30,
        "default": 120
    }

    def __init__(self):
        self.sensor_reliability: Dict[str, float] = {"default": 0.5}

    def set_reliability(self, sensor_id: str, score: float):
        """Set reliability score for a specific sensor."""
        if not 0.0 <= score <= 1.0:
            raise ValueError("Reliability score must be between 0.0 and 1.0")
        self.sensor_reliability[sensor_id] = score

    def _get_half_life(self, sensor_type: str) -> float:
        """Get half-life for sensor type."""
        return self.HALF_LIFE.get(sensor_type, self.HALF_LIFE["default"])

    def fuse_temperature(self, readings: List[Tuple[str, float, float]], sensor_type: str = "temperature") -> Optional[float]:
        """Fuse multiple temperature readings with weighted average."""
        if not readings:
            return None
        total_weight = 0.0
        weighted_sum = 0.0
        current_time = time.time()
        half_life = self._get_half_life(sensor_type)
        for sensor_id, value, timestamp in readings:
            age_seconds = current_time - timestamp
            age_factor = math.exp(-age_seconds / half_life)
            reliability = self.sensor_reliability.get(sensor_id, self.sensor_reliability["default"])
            weight = reliability * age_factor
            weighted_sum += value * weight
            total_weight += weight
        if total_weight == 0:
            return None
        return weighted_sum / total_weight

    def fuse_generic(self, readings: List[Tuple[str, float, float]], sensor_type: str = "default") -> Optional[float]:
        """Generic sensor fusion with sensor-type specific half-life."""
        return self.fuse_temperature(readings, sensor_type)

    def integrate_occupancy(self, vision_count: int, pir_active: bool, zone_size: float = 20.0) -> int:
        """Integrate occupancy from YOLO vision and PIR sensor."""
        estimated_count = vision_count
        if pir_active and vision_count == 0:
            estimated_count = 1
        if zone_size > 50 and vision_count > 0:
            estimated_count = int(vision_count * 1.2)
        return estimated_count


# ── Trend Detector ──────────────────────────────────────────────────


class TrendDetector:
    """Detects trends (rising/falling/stable) for analog channels."""

    WINDOW_SEC = 300  # 5 minutes

    THRESHOLDS: Dict[str, float] = {
        "temperature": 0.5,
        "humidity": 3.0,
        "co2": 50,
        "pressure": 1.0,
        "illuminance": 50,
        "default": 1.0,
    }

    def __init__(self):
        self._history: Dict[str, List[Tuple[float, float]]] = {}

    def record(self, key: str, value: float, timestamp: float):
        if key not in self._history:
            self._history[key] = []
        self._history[key].append((timestamp, value))
        cutoff = timestamp - 600
        self._history[key] = [(t, v) for t, v in self._history[key] if t >= cutoff]

    def get_trend(self, key: str, current_value: float, channel: str) -> str:
        """Returns 'rising', 'falling', or 'stable'."""
        history = self._history.get(key, [])
        if len(history) < 2:
            return "stable"
        now = history[-1][0]
        window_start = now - self.WINDOW_SEC
        old_readings = [(t, v) for t, v in history if t <= window_start + 30]
        if not old_readings:
            return "stable"
        old_value = old_readings[0][1]
        threshold = self.THRESHOLDS.get(channel, self.THRESHOLDS["default"])
        diff = current_value - old_value
        if diff > threshold:
            return "rising"
        elif diff < -threshold:
            return "falling"
        return "stable"


# ── Event Counter ───────────────────────────────────────────────────


class EventCounter:
    """Counts events (motion triggers, etc.) within a rolling time window."""

    WINDOW_SEC = 300  # 5 minutes

    def __init__(self):
        self._events: Dict[str, List[float]] = {}

    def record_event(self, key: str, timestamp: float):
        if key not in self._events:
            self._events[key] = []
        self._events[key].append(timestamp)
        self._trim(key, timestamp)

    def record_count(self, key: str, count: int, timestamp: float):
        """Record a pre-aggregated count (e.g. motion_count from Z2M Bridge)."""
        if key not in self._events:
            self._events[key] = []
        for _ in range(int(count)):
            self._events[key].append(timestamp)
        self._trim(key, timestamp)

    def get_count(self, key: str, window_sec: Optional[float] = None) -> int:
        window = window_sec or self.WINDOW_SEC
        if key not in self._events:
            return 0
        cutoff = time.time() - window
        return sum(1 for t in self._events[key] if t >= cutoff)

    def get_frequency_per_min(self, key: str) -> float:
        count = self.get_count(key)
        return count / (self.WINDOW_SEC / 60)

    def _trim(self, key: str, now: float):
        cutoff = now - self.WINDOW_SEC
        self._events[key] = [t for t in self._events[key] if t >= cutoff]


# ── State Tracker ───────────────────────────────────────────────────


class StateTracker:
    """Tracks binary sensor states with transition timestamps."""

    def __init__(self):
        self._states: Dict[str, Dict] = {}
        self._change_times: Dict[str, List[float]] = {}

    def update(self, key: str, state: bool, timestamp: float) -> bool:
        """Update state. Returns True if state changed."""
        if key not in self._states:
            self._states[key] = {"state": state, "since": timestamp}
            self._change_times[key] = []
            return True

        prev = self._states[key]["state"]
        if state != prev:
            self._states[key]["state"] = state
            self._states[key]["since"] = timestamp
            self._change_times.setdefault(key, []).append(timestamp)
            cutoff = timestamp - 3600
            self._change_times[key] = [t for t in self._change_times[key] if t >= cutoff]
            return True
        return False

    def get_state(self, key: str) -> Optional[Dict]:
        """Get current state, duration, and change count."""
        if key not in self._states:
            return None
        info = self._states[key]
        duration = time.time() - info["since"]
        changes_1h = len(self._change_times.get(key, []))
        return {
            "state": info["state"],
            "since": info["since"],
            "duration_sec": duration,
            "changes_1h": changes_1h,
        }
