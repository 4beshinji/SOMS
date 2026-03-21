"""
Data classes for World Model state representation.
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime
import time


class EnvironmentData(BaseModel):
    """Environmental sensor data for a zone."""
    temperature: Optional[float] = None  # Celsius
    humidity: Optional[float] = None  # Percentage
    co2: Optional[int] = None  # ppm
    illuminance: Optional[float] = None  # lux
    pressure: Optional[float] = None  # hPa
    gas_resistance: Optional[int] = None  # Ohms (BME680 VOC indicator)
    soil_moisture: Optional[float] = None  # Percentage
    soil_temperature: Optional[float] = None  # Celsius

    # Trend indicators per channel: "stable" | "rising" | "falling"
    trends: Dict[str, str] = Field(default_factory=dict)

    # Timestamps for each measurement
    timestamps: Dict[str, float] = Field(default_factory=dict)
    
    @property
    def is_stuffy(self) -> bool:
        """CO2 concentration exceeds 1000ppm threshold."""
        return self.co2 is not None and self.co2 > 1000
    
    @property
    def thermal_comfort(self) -> str:
        """Thermal comfort level: cold | comfortable | hot."""
        if self.temperature is None:
            return "unknown"
        if self.temperature < 18:
            return "cold"
        elif self.temperature > 26:
            return "hot"
        return "comfortable"


class OccupancyData(BaseModel):
    """Occupancy state including activity classification."""
    person_count: int = 0
    vision_count: int = 0  # From YOLO
    pir_detected: bool = False  # From PIR sensor

    # Activity distribution (active/focused)
    activity_distribution: Dict[str, int] = Field(default_factory=dict)
    avg_motion_level: float = 0.0  # 0.0 - 1.0

    # Perception ActivityMonitor data
    activity_level: float = 0.0            # 0.0-1.0 (short-term motion)
    activity_class: str = "unknown"        # "idle"|"low"|"moderate"|"high"
    posture_duration_sec: float = 0.0      # Current posture duration (seconds)
    posture_status: str = "unknown"        # "changing"|"mostly_static"|"static"

    # Event-based motion tracking
    motion_event_count_5min: int = 0
    motion_frequency_per_min: float = 0.0

    # State-based presence tracking
    presence_state: Optional[bool] = None
    presence_duration_sec: float = 0.0

    # Door state tracking: {device_id: {"open": bool, "duration_sec": float, "changes_1h": int}}
    door_states: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Temporal statistics
    last_entry_time: Optional[float] = None
    last_exit_time: Optional[float] = None
    
    @property
    def is_occupied(self) -> bool:
        return self.person_count > 0
    
    @property
    def dominant_activity(self) -> str:
        """Most common activity state."""
        if not self.activity_distribution:
            return "unknown"
        return max(self.activity_distribution, key=self.activity_distribution.get)
    
    @property
    def activity_summary(self) -> str:
        """Human-readable activity summary."""
        if self.person_count == 0:
            return "無人"
        
        active = self.activity_distribution.get("active", 0)
        focused = self.activity_distribution.get("focused", 0)
        
        if active > focused:
            return f"{self.person_count}人が活発に活動中"
        else:
            return f"{self.person_count}人が集中作業中"


class DeviceState(BaseModel):
    """State of a controllable device."""
    device_id: str
    device_type: str  # "hvac", "light", "coffee_machine", etc.
    
    is_online: bool = True
    power_state: str = "off"  # "on" | "off" | "standby"
    
    # Device-specific state (e.g., {"mode": "cooling", "target_temp": 24})
    specific_state: Dict[str, Any] = Field(default_factory=dict)
    
    # Command history
    last_command: Optional[str] = None
    last_command_time: Optional[float] = None


class Event(BaseModel):
    """Event record for zone history."""
    timestamp: float
    event_type: str  # "person_entered", "temp_spike", "co2_threshold_exceeded", etc.
    severity: str  # "info" | "warning" | "critical"
    data: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def description(self) -> str:
        """Auto-generated event description."""
        if self.event_type == "person_entered":
            return f"{self.data.get('count', 0)}人が入室しました"
        elif self.event_type == "person_exited":
            return f"{self.data.get('count', 0)}人が退室しました"
        elif self.event_type == "co2_threshold_exceeded":
            return f"CO2濃度が{self.data.get('value', 0)}ppmに達しました（換気推奨）"
        elif self.event_type == "temp_spike":
            return f"気温が急上昇しました（{self.data.get('value', 0)}℃）"
        elif self.event_type == "sedentary_alert":
            minutes = int(self.data.get('duration_sec', 0) / 60)
            return f"同じ姿勢で{minutes}分以上座り続けています"
        elif self.event_type == "sensor_tamper":
            channel = self.data.get('channel', '?')
            change = self.data.get('change', 0)
            return f"センサー異常: {channel}が急変({change:.1f}変化)"
        elif self.event_type == "door_opened":
            return f"ドアが開きました ({self.data.get('device_id', '')})"
        elif self.event_type == "door_closed":
            return f"ドアが閉まりました ({self.data.get('device_id', '')})"
        elif self.event_type == "fall_detected":
            conf = self.data.get("confidence", 0)
            dur = self.data.get("duration_sec", 0)
            return f"転倒検知: 信頼度{conf:.0%}、{dur:.0f}秒経過 ⚠️緊急"
        elif self.event_type == "task_report":
            status_labels = {
                "no_issue": "問題なし",
                "resolved": "対応済み",
                "needs_followup": "要追加対応",
                "cannot_resolve": "対応不可",
            }
            title = self.data.get("title", "タスク")
            status = status_labels.get(self.data.get("report_status", ""), self.data.get("report_status", ""))
            note = self.data.get("completion_note", "")
            desc = f"「{title}」→ {status}"
            if note:
                desc += f": {note}"
            return desc
        elif self.event_type == "vlm_analysis":
            atype = self.data.get("analysis_type", "")
            content = self.data.get("content", "")
            return f"VLM分析({atype}): {content[:100]}"
        return f"イベント: {self.event_type}"


class SpatialDetection(BaseModel):
    """A single detected object with pixel-space position."""
    class_name: str = "person"
    center_px: List[float] = Field(default_factory=list)   # [cx, cy]
    bbox_px: List[float] = Field(default_factory=list)      # [x1, y1, x2, y2]
    confidence: float = 0.0
    track_id: Optional[int] = None          # Per-camera BoT-SORT local ID
    global_id: Optional[int] = None         # Cross-camera global ID
    floor_position_m: Optional[List[float]] = None  # [x_m, y_m] floor coords


class TrackedPersonData(BaseModel):
    """A single person tracked across cameras."""
    global_id: int
    floor_x_m: float = 0.0
    floor_y_m: float = 0.0
    zone: str = ""
    cameras: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    duration_sec: float = 0.0


class TrackingData(BaseModel):
    """Cross-camera tracking state for a zone."""
    persons: List[TrackedPersonData] = Field(default_factory=list)
    person_count: int = 0
    last_update: float = 0.0


class ZoneSpatialData(BaseModel):
    """Real-time spatial detection data for a zone."""
    camera_id: Optional[str] = None
    image_size: List[int] = Field(default_factory=lambda: [640, 480])
    persons: List[SpatialDetection] = Field(default_factory=list)
    objects: List[SpatialDetection] = Field(default_factory=list)
    last_spatial_update: float = 0.0
    heatmap_counts: List[List[int]] = Field(default_factory=list)  # grid_rows × grid_cols
    heatmap_window_start: float = 0.0


class ZoneMetadata(BaseModel):
    """Static spatial metadata for a zone (from config/spatial.yaml)."""
    display_name: str = ""
    polygon: List[List[float]] = Field(default_factory=list)
    area_m2: float = 0.0
    floor: int = 1
    adjacent_zones: List[str] = Field(default_factory=list)
    grid_cols: int = 10
    grid_rows: int = 10


class ZoneState(BaseModel):
    """Complete state of a zone (room/area)."""
    zone_id: str
    region_id: str = "local"

    environment: EnvironmentData = Field(default_factory=EnvironmentData)
    occupancy: OccupancyData = Field(default_factory=OccupancyData)
    devices: Dict[str, DeviceState] = Field(default_factory=dict)
    spatial: ZoneSpatialData = Field(default_factory=ZoneSpatialData)
    tracking: TrackingData = Field(default_factory=TrackingData)
    metadata: ZoneMetadata = Field(default_factory=ZoneMetadata)
    
    # Event history (recent events only)
    events: List[Event] = Field(default_factory=list)

    # Passthrough sensor data for unknown/generic channels
    extra_sensors: Dict[str, float] = Field(default_factory=dict)

    # Metadata
    last_update: float = Field(default_factory=time.time)
    
    # Internal cache for change detection
    _prev_occupancy: int = 0
    _prev_temperature: Optional[float] = None
    _prev_humidity: Optional[float] = None
    _prev_door_state: Optional[bool] = None
    _prev_env_timestamps: Dict[str, float] = {}
    
    class Config:
        # Pydantic V2: Private attributes automatically work with underscore prefix
        from_attributes = True
