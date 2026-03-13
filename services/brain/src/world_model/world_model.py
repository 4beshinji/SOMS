"""
World Model: Centralized state management for office environment.
"""
import json
import logging
import time
from typing import Dict, Optional, List
from .data_classes import (
    ZoneState, EnvironmentData, OccupancyData, DeviceState, Event,
    SpatialDetection, ZoneSpatialData, ZoneMetadata,
    TrackedPersonData, TrackingData,
)
from .sensor_fusion import SensorFusion

logger = logging.getLogger(__name__)


MAX_EVENTS_PER_ZONE = 100


class WorldModel:
    """
    Maintains the unified state of all zones in the office.
    Integrates sensor data, occupancy information, and device states.
    """

    # Default suppression duration (seconds) per alert type.
    # Slow-changing conditions get longer suppression.
    SUPPRESSION_DEFAULTS: Dict[str, float] = {
        "high_temp": 1800,   # 30 min — AC takes time
        "low_temp": 1800,    # 30 min — heating takes time
        "high_co2": 600,     # 10 min — ventilation is faster
        "low_humidity": 1200, # 20 min
        "high_humidity": 1200,
        "low_stock": 3600,   # 1 hour — shopping takes time
    }

    def __init__(self, spatial_config=None):
        self.zones: Dict[str, ZoneState] = {}
        self.sensor_fusion = SensorFusion()

        # Optional event store writer (set by Brain after init)
        self.event_writer = None

        # Optional inventory tracker (set by Brain after init)
        self.inventory_tracker = None

        # Cache for LLM context (optimization)
        self._llm_context_cache: Optional[str] = None
        self._cache_timestamp: float = 0

        # Sensor readings buffer for fusion
        self._sensor_readings: Dict[str, List] = {}

        # Alert suppression: {(zone_id, alert_type): expiry_timestamp}
        # Prevents repeated task creation for slow-changing conditions.
        self._suppressed_alerts: Dict[tuple, float] = {}

        # Spatial config
        self._spatial_config = spatial_config
        if spatial_config:
            self._apply_spatial_config(spatial_config)

    def apply_spatial_config(self, config):
        """Public method: (re-)apply spatial config after init (e.g. from REST)."""
        self._spatial_config = config
        self._apply_spatial_config(config)

    def _apply_spatial_config(self, config):
        """Apply spatial configuration to pre-create zones with metadata."""
        for zone_id, geom in config.zones.items():
            if zone_id not in self.zones:
                self.zones[zone_id] = ZoneState(zone_id=zone_id)
            zone = self.zones[zone_id]
            zone.metadata = ZoneMetadata(
                display_name=geom.display_name,
                polygon=geom.polygon,
                area_m2=geom.area_m2,
                floor=geom.floor,
                adjacent_zones=geom.adjacent_zones,
                grid_cols=geom.grid_cols,
                grid_rows=geom.grid_rows,
            )
            # Initialize heatmap grid
            zone.spatial.heatmap_counts = [
                [0] * geom.grid_cols for _ in range(geom.grid_rows)
            ]
            zone.spatial.heatmap_window_start = time.time()
        logger.info("Spatial config applied: %d zones pre-created", len(config.zones))

    def _add_event(self, zone: ZoneState, event: Event):
        """Append an event to a zone, trimming oldest entries if over limit."""
        zone.events.append(event)
        if len(zone.events) > MAX_EVENTS_PER_ZONE:
            zone.events = zone.events[-MAX_EVENTS_PER_ZONE:]

        # Forward to event store if available
        if self.event_writer:
            try:
                self.event_writer.record_world_event(
                    zone=zone.zone_id,
                    event_type=event.event_type,
                    severity=event.severity,
                    data=event.data,
                )
            except Exception:
                pass  # Non-blocking — never disrupt WorldModel
    
    def suppress_alert(self, zone_id: str, alert_type: str, duration: float = None):
        """
        Suppress an alert for a zone. Used after creating a task so the
        same condition doesn't trigger another task while the physical
        environment slowly changes (e.g., AC cooling a room).

        Args:
            zone_id: Zone identifier
            alert_type: One of high_temp, low_temp, high_co2, low_humidity, high_humidity
            duration: Suppression duration in seconds (defaults per alert type)
        """
        if duration is None:
            duration = self.SUPPRESSION_DEFAULTS.get(alert_type, 1800)
        key = (zone_id, alert_type)
        self._suppressed_alerts[key] = time.time() + duration
        self._llm_context_cache = None  # Invalidate cache
        logger.info("Alert suppressed: zone=%s type=%s duration=%ds", zone_id, alert_type, duration)

    def _is_suppressed(self, zone_id: str, alert_type: str) -> bool:
        """Check if an alert is currently suppressed."""
        key = (zone_id, alert_type)
        expiry = self._suppressed_alerts.get(key)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._suppressed_alerts[key]
            return False
        return True

    def clear_suppression(self, zone_id: str, alert_type: str):
        """Manually clear a suppression (e.g., when condition resolves)."""
        key = (zone_id, alert_type)
        if key in self._suppressed_alerts:
            del self._suppressed_alerts[key]
            self._llm_context_cache = None

    def update_from_mqtt(self, topic: str, payload: dict):
        """
        Update world model from MQTT message.
        
        Args:
            topic: MQTT topic (e.g., "office/kitchen/sensor/temp_01/temperature")
            payload: Message payload (JSON dict)
        """
        parsed = self._parse_topic(topic)
        if not parsed:
            logger.debug(f"Ignoring non-office topic: {topic}")
            return
        
        zone_id = parsed["zone"]
        device_type = parsed["device_type"]
        device_id = parsed.get("device_id")
        channel = parsed.get("channel")
        
        # Create zone if it doesn't exist
        if zone_id not in self.zones:
            self.zones[zone_id] = ZoneState(zone_id=zone_id)
            logger.info(f"Created new zone: {zone_id}")
        
        zone = self.zones[zone_id]
        
        # Route to appropriate handler
        if device_type == "sensor":
            if channel == "status":
                # Bulk payload: {"temperature": X, "humidity": Y, ...}
                # Fan out each key as an individual channel update.
                _KNOWN_CHANNELS = {
                    "temperature", "humidity", "co2", "pressure",
                    "gas", "gas_resistance", "illuminance", "motion", "door",
                }
                for key, val in payload.items():
                    if key in _KNOWN_CHANNELS:
                        ch = "gas_resistance" if key == "gas" else key
                        self._update_environment(
                            zone, ch, {"value": val}, device_id
                        )
            else:
                self._update_environment(zone, channel, payload, device_id)
        elif device_type in ("camera", "occupancy"):
            self._update_occupancy(zone, payload)
        elif device_type == "activity":
            self._update_activity(zone, payload)
        elif device_type == "spatial":
            self._update_spatial(zone, payload, device_id)
        elif device_type == "tracking":
            self._update_tracking(zone, payload)
        elif device_type == "safety":
            self._update_safety(zone, payload, channel)
        elif device_type == "task_report":
            self._handle_task_report(zone, payload, device_id)
        elif device_type == "anomaly":
            self._update_anomaly(zone, payload, channel)
        elif device_type in ["hvac", "light", "coffee_machine"]:
            self._update_device(zone, device_type, device_id, payload)
        
        zone.last_update = time.time()
        
        # Detect events based on state changes
        self._detect_events(zone)
        
        # Invalidate LLM context cache
        self._llm_context_cache = None
    
    def _parse_topic(self, topic: str) -> Optional[Dict[str, str]]:
        """
        Parse MQTT topic into components.
        
        Format: office/{zone}/{device_type}/{device_id}/{channel}
        Example: office/meeting_room_a/sensor/env_01/temperature
        
        Returns:
            Dict with zone, device_type, device_id, channel or None
        """
        parts = topic.split('/')
        if len(parts) < 3 or parts[0] != "office":
            return None
        
        return {
            "zone": parts[1],
            "device_type": parts[2],
            "device_id": parts[3] if len(parts) > 3 else None,
            "channel": parts[4] if len(parts) > 4 else None
        }
    
    def _update_environment(self, zone: ZoneState, channel: str, payload: dict, device_id: str):
        """Update environmental data for a zone."""
        current_time = time.time()
        
        # Extract value from payload
        value = payload.get(channel) or payload.get("value")
        if value is None:
            return
        
        # Store reading for sensor fusion
        reading_key = f"{zone.zone_id}:{channel}"
        if reading_key not in self._sensor_readings:
            self._sensor_readings[reading_key] = []
        
        self._sensor_readings[reading_key].append((device_id, value, current_time))
        
        # Keep only recent readings (last 10 minutes)
        self._sensor_readings[reading_key] = [
            r for r in self._sensor_readings[reading_key]
            if current_time - r[2] < 600
        ]
        
        # Fuse multiple sensor readings with appropriate sensor type
        fused_value = self.sensor_fusion.fuse_generic(
            self._sensor_readings[reading_key], 
            sensor_type=channel  # Pass sensor type for half-life selection
        )
        
        if fused_value is None:
            return
        
        # Update zone environment
        if channel == "temperature":
            zone.environment.temperature = fused_value
        elif channel == "humidity":
            zone.environment.humidity = fused_value
        elif channel == "co2":
            zone.environment.co2 = int(fused_value)
        elif channel == "illuminance":
            zone.environment.illuminance = fused_value
        elif channel == "pressure":
            zone.environment.pressure = fused_value
        elif channel == "gas_resistance":
            zone.environment.gas_resistance = int(fused_value)
        elif channel == "motion":
            zone.occupancy.pir_detected = bool(fused_value)
            zone.occupancy.person_count = self.sensor_fusion.integrate_occupancy(
                vision_count=zone.occupancy.vision_count,
                pir_active=zone.occupancy.pir_detected
            )
        elif channel == "door":
            prev_door = getattr(zone, '_prev_door_state', None)
            door_open = bool(fused_value)
            if prev_door is not None and door_open != prev_door:
                event = Event(
                    timestamp=current_time,
                    event_type="door_opened" if door_open else "door_closed",
                    severity="info",
                    data={"device_id": device_id, "state": "open" if door_open else "closed"}
                )
                self._add_event(zone, event)
            zone._prev_door_state = door_open
        elif channel == "weight" and self.inventory_tracker:
            inv_event = self.inventory_tracker.update_weight(
                zone.zone_id, device_id, channel, fused_value,
            )
            if inv_event:
                severity = "warning" if inv_event.event_type == "low_stock" else "info"
                event = Event(
                    timestamp=current_time,
                    event_type=inv_event.event_type,
                    severity=severity,
                    data={
                        "item_name": inv_event.item_name,
                        "category": inv_event.category,
                        "quantity": inv_event.quantity,
                        "min_threshold": inv_event.min_threshold,
                        "reorder_quantity": inv_event.reorder_quantity,
                        "device_id": device_id,
                        "store": inv_event.store,
                        "price": inv_event.price,
                    },
                )
                self._add_event(zone, event)
        elif channel == "barcode" and self.inventory_tracker:
            barcode_value = str(fused_value) if fused_value else ""
            if barcode_value:
                inv_event = self.inventory_tracker.handle_barcode_scan(
                    device_id, "weight", barcode_value,
                )
                if inv_event:
                    event = Event(
                        timestamp=current_time,
                        event_type=inv_event.event_type,
                        severity="info",
                        data={
                            "item_name": inv_event.item_name,
                            "barcode": barcode_value,
                            "quantity": inv_event.quantity,
                            "device_id": device_id,
                        },
                    )
                    self._add_event(zone, event)

        # Update timestamp
        zone.environment.timestamps[channel] = current_time
    
    def _update_occupancy(self, zone: ZoneState, payload: dict):
        """Update occupancy data from camera/vision system."""
        # Handle different payload formats
        if "person_count" in payload:
            zone.occupancy.vision_count = payload["person_count"]
        elif "count" in payload:
            zone.occupancy.vision_count = payload["count"]
        elif "occupancy" in payload:
            zone.occupancy.vision_count = 1 if payload["occupancy"] else 0
        
        # Activity distribution (from activity classification)
        if "activity_distribution" in payload:
            zone.occupancy.activity_distribution = payload["activity_distribution"]
        
        if "avg_motion_level" in payload:
            zone.occupancy.avg_motion_level = payload["avg_motion_level"]
        
        # Integrate with PIR if available
        zone.occupancy.person_count = self.sensor_fusion.integrate_occupancy(
            vision_count=zone.occupancy.vision_count,
            pir_active=zone.occupancy.pir_detected
        )
    
    def _update_activity(self, zone: ZoneState, payload: dict):
        """Update activity data from Perception ActivityMonitor."""
        if "person_count" in payload:
            zone.occupancy.vision_count = payload["person_count"]
            zone.occupancy.person_count = self.sensor_fusion.integrate_occupancy(
                vision_count=payload["person_count"],
                pir_active=zone.occupancy.pir_detected
            )
        if "activity_level" in payload:
            zone.occupancy.activity_level = payload["activity_level"]
        if "activity_class" in payload:
            zone.occupancy.activity_class = payload["activity_class"]
        if "posture_duration_sec" in payload:
            zone.occupancy.posture_duration_sec = payload["posture_duration_sec"]
        if "posture_status" in payload:
            zone.occupancy.posture_status = payload["posture_status"]

    def _update_spatial(self, zone: ZoneState, payload: dict, camera_id: str):
        """Update spatial detection data from Perception spatial publish."""
        current_time = time.time()
        zone.spatial.camera_id = payload.get("camera_id", camera_id)
        zone.spatial.image_size = payload.get("image_size", [640, 480])
        zone.spatial.last_spatial_update = current_time

        # Parse person detections (with optional tracking fields)
        zone.spatial.persons = [
            SpatialDetection(
                class_name="person",
                center_px=p.get("center_px", []),
                bbox_px=p.get("bbox_px", []),
                confidence=p.get("confidence", 0.0),
                track_id=p.get("track_id"),
                global_id=p.get("global_id"),
                floor_position_m=p.get("floor_position_m"),
            )
            for p in payload.get("persons", [])
        ]

        # Parse object detections
        zone.spatial.objects = [
            SpatialDetection(
                class_name=o.get("class_name", "unknown"),
                center_px=o.get("center_px", []),
                bbox_px=o.get("bbox_px", []),
                confidence=o.get("confidence", 0.0),
            )
            for o in payload.get("objects", [])
        ]

        # Accumulate heatmap
        self._accumulate_heatmap(zone, current_time)

        # Record to event store
        if self.event_writer:
            try:
                self.event_writer.record_spatial_snapshot(
                    zone=zone.zone_id,
                    camera_id=zone.spatial.camera_id,
                    data={
                        "image_size": zone.spatial.image_size,
                        "person_count": len(zone.spatial.persons),
                        "object_count": len(zone.spatial.objects),
                        "persons": [p.model_dump() for p in zone.spatial.persons],
                        "objects": [o.model_dump() for o in zone.spatial.objects],
                    },
                )
            except Exception:
                pass  # Non-blocking

    def _update_tracking(self, zone: ZoneState, payload: dict):
        """Update cross-camera tracking data from MTMCPublisher."""
        zone.tracking.person_count = payload.get("person_count", 0)
        zone.tracking.last_update = time.time()
        zone.tracking.persons = [
            TrackedPersonData(**p) for p in payload.get("persons", [])
        ]
        # Tracking provides more accurate occupancy than single-camera vision
        zone.occupancy.vision_count = zone.tracking.person_count
        zone.occupancy.person_count = self.sensor_fusion.integrate_occupancy(
            vision_count=zone.tracking.person_count,
            pir_active=zone.occupancy.pir_detected,
        )

    def _update_safety(self, zone: ZoneState, payload: dict, channel: str):
        """Handle safety events (e.g., fall detection)."""
        if channel == "fall":
            conf = payload.get("confidence", 0)
            duration = payload.get("duration_sec", 0)
            event = Event(
                timestamp=time.time(),
                event_type="fall_detected",
                severity="critical",
                data={
                    "confidence": conf,
                    "duration_sec": duration,
                    "bbox": payload.get("bbox", []),
                    "tracker_id": payload.get("tracker_id"),
                }
            )
            self._add_event(zone, event)
            logger.warning(
                "Fall detected in %s: confidence=%.2f duration=%.1fs",
                zone.zone_id, conf, duration,
            )

    def _update_anomaly(self, zone: ZoneState, payload: dict, channel: str):
        """Handle anomaly detection events from the anomaly service."""
        event = Event(
            timestamp=time.time(),
            event_type="anomaly_detected",
            severity=payload.get("severity", "warning"),
            data={
                "channel": channel,
                "score": payload.get("score"),
                "predicted": payload.get("predicted"),
                "actual": payload.get("actual"),
                "source": payload.get("source", "batch"),
            }
        )
        self._add_event(zone, event)
        logger.warning(
            "Anomaly detected in %s [%s]: score=%.1f predicted=%.1f actual=%.1f (%s)",
            zone.zone_id, channel,
            payload.get("score", 0), payload.get("predicted", 0),
            payload.get("actual", 0), payload.get("severity", "warning"),
        )

    def _accumulate_heatmap(self, zone: ZoneState, current_time: float):
        """Map pixel-space person positions to grid cells for heatmap."""
        # Reset heatmap every hour
        if current_time - zone.spatial.heatmap_window_start >= 3600:
            rows = zone.metadata.grid_rows or 10
            cols = zone.metadata.grid_cols or 10
            zone.spatial.heatmap_counts = [[0] * cols for _ in range(rows)]
            zone.spatial.heatmap_window_start = current_time

        if not zone.spatial.heatmap_counts:
            return

        img_w, img_h = zone.spatial.image_size
        rows = len(zone.spatial.heatmap_counts)
        cols = len(zone.spatial.heatmap_counts[0]) if rows > 0 else 0
        if rows == 0 or cols == 0 or img_w == 0 or img_h == 0:
            return

        for person in zone.spatial.persons:
            if len(person.center_px) < 2:
                continue
            cx, cy = person.center_px
            grid_col = int(cx / img_w * cols)
            grid_row = int(cy / img_h * rows)
            grid_col = max(0, min(grid_col, cols - 1))
            grid_row = max(0, min(grid_row, rows - 1))
            zone.spatial.heatmap_counts[grid_row][grid_col] += 1

    def _update_device(self, zone: ZoneState, device_type: str, device_id: str, payload: dict):
        """Update device state."""
        if device_id not in zone.devices:
            zone.devices[device_id] = DeviceState(
                device_id=device_id,
                device_type=device_type
            )
        
        device = zone.devices[device_id]
        
        # Update power state
        if "power_state" in payload:
            device.power_state = payload["power_state"]
        elif "state" in payload:
            device.power_state = payload["state"]
        
        # Update specific state
        if "mode" in payload or "target_temp" in payload:
            device.specific_state.update(payload)
    
    def _handle_task_report(self, zone: ZoneState, payload: dict, device_id: str):
        """Handle task completion report from dashboard."""
        event = Event(
            timestamp=time.time(),
            event_type="task_report",
            severity="info",
            data={
                "task_id": payload.get("task_id", device_id),
                "title": payload.get("title", ""),
                "report_status": payload.get("report_status", "unknown"),
                "completion_note": payload.get("completion_note", ""),
            }
        )
        self._add_event(zone, event)
        logger.info("Task report received: task_id=%s status=%s",
                     payload.get("task_id"), payload.get("report_status"))

    def _detect_events(self, zone: ZoneState):
        """Detect events based on state changes."""
        current_time = time.time()

        # Capture previous env values before they are updated below
        saved_prev_temperature = zone._prev_temperature
        saved_prev_humidity = zone._prev_humidity

        # Person count change
        if zone.occupancy.person_count != zone._prev_occupancy:
            if zone.occupancy.person_count > zone._prev_occupancy:
                event = Event(
                    timestamp=current_time,
                    event_type="person_entered",
                    severity="info",
                    data={"count": zone.occupancy.person_count}
                )
                self._add_event(zone, event)
                zone.occupancy.last_entry_time = current_time
            elif zone.occupancy.person_count < zone._prev_occupancy:
                event = Event(
                    timestamp=current_time,
                    event_type="person_exited",
                    severity="info",
                    data={"count": zone.occupancy.person_count}
                )
                self._add_event(zone, event)
                if zone.occupancy.person_count == 0:
                    zone.occupancy.last_exit_time = current_time
            
            zone._prev_occupancy = zone.occupancy.person_count
        
        # CO2 threshold exceeded
        if zone.environment.co2 and zone.environment.co2 > 1000:
            # Avoid duplicate events (don't create if one exists in last 10 minutes)
            recent_co2_events = [
                e for e in zone.events
                if e.event_type == "co2_threshold_exceeded"
                and current_time - e.timestamp < 600
            ]
            if not recent_co2_events:
                event = Event(
                    timestamp=current_time,
                    event_type="co2_threshold_exceeded",
                    severity="warning",
                    data={"value": zone.environment.co2}
                )
                self._add_event(zone, event)

        # Auto-clear CO2 suppression when condition resolves
        if zone.environment.co2 is not None and zone.environment.co2 <= 1000:
            self.clear_suppression(zone.zone_id, "high_co2")

        # Temperature spike (with 600s cooldown, matching CO2)
        if zone.environment.temperature and zone._prev_temperature:
            temp_change = abs(zone.environment.temperature - zone._prev_temperature)
            if temp_change > 3.0:  # 3°C change
                recent_temp_spikes = [
                    e for e in zone.events
                    if e.event_type == "temp_spike"
                    and current_time - e.timestamp < 600
                ]
                if not recent_temp_spikes:
                    event = Event(
                        timestamp=current_time,
                        event_type="temp_spike",
                        severity="warning",
                        data={"value": zone.environment.temperature, "change": temp_change}
                    )
                    self._add_event(zone, event)

        # Auto-clear temperature suppression when condition resolves
        if zone.environment.temperature is not None:
            if 18 <= zone.environment.temperature <= 26:
                self.clear_suppression(zone.zone_id, "high_temp")
                self.clear_suppression(zone.zone_id, "low_temp")

        zone._prev_temperature = zone.environment.temperature

        # Sedentary alert: static posture for >= 30 minutes with people present
        if (zone.occupancy.person_count > 0
                and zone.occupancy.posture_status == "static"
                and zone.occupancy.posture_duration_sec >= 1800):
            recent_sedentary = [
                e for e in zone.events
                if e.event_type == "sedentary_alert"
                and current_time - e.timestamp < 3600  # 1 hour cooldown
            ]
            if not recent_sedentary:
                event = Event(
                    timestamp=current_time,
                    event_type="sedentary_alert",
                    severity="info",
                    data={
                        "duration_sec": zone.occupancy.posture_duration_sec,
                        "person_count": zone.occupancy.person_count,
                    }
                )
                self._add_event(zone, event)

        # Sensor tamper: rapid environment change (use saved previous values)
        for channel, prev_val, threshold in [
            ("temperature", saved_prev_temperature, 5.0),
            ("humidity", saved_prev_humidity, 20.0),
        ]:
            current_val = getattr(zone.environment, channel, None)
            ts_key = channel
            current_ts = zone.environment.timestamps.get(ts_key)
            prev_ts = zone._prev_env_timestamps.get(ts_key)

            if (current_val is not None and prev_val is not None
                    and current_ts is not None and prev_ts is not None):
                dt = current_ts - prev_ts
                if 0 < dt <= 30:
                    change = abs(current_val - prev_val)
                    if change >= threshold:
                        recent_tamper = [
                            e for e in zone.events
                            if e.event_type == "sensor_tamper"
                            and current_time - e.timestamp < 300  # 5 min cooldown
                        ]
                        if not recent_tamper:
                            event = Event(
                                timestamp=current_time,
                                event_type="sensor_tamper",
                                severity="warning",
                                data={
                                    "channel": channel,
                                    "change": change,
                                    "duration_sec": dt,
                                    "value": current_val,
                                }
                            )
                            self._add_event(zone, event)

            if current_val is not None:
                if channel == "humidity":
                    zone._prev_humidity = current_val
            if current_ts is not None:
                zone._prev_env_timestamps[ts_key] = current_ts

        # Limit event history size (keep last 50 events per zone)
        if len(zone.events) > 50:
            zone.events = zone.events[-50:]
    
    def get_zone(self, zone_id: str) -> Optional[ZoneState]:
        """Get state of a specific zone."""
        return self.zones.get(zone_id)
    
    def get_all_zones(self) -> Dict[str, ZoneState]:
        """Get all zones."""
        return self.zones
    
    def get_llm_context(self) -> str:
        """
        Generate optimized context string for LLM.
        Cached for 5 seconds to avoid redundant generation.
        """
        current_time = time.time()
        
        # Return cached context if fresh
        if self._llm_context_cache and (current_time - self._cache_timestamp < 5):
            return self._llm_context_cache
        
        context_parts = []

        # Collect alerts for abnormal values across all zones.
        # Suppressed alerts (task already created, waiting for condition to resolve)
        # are shown as "対応中" instead of "要対応" so the LLM doesn't create duplicates.
        alerts = []
        suppressed = []
        for zone_id, zone in sorted(self.zones.items()):
            env = zone.environment
            if env.temperature is not None:
                if env.temperature > 26:
                    msg = f"[{zone_id}] 高温: {env.temperature:.1f}℃（基準: 18-26℃）"
                    if self._is_suppressed(zone_id, "high_temp"):
                        suppressed.append(f"🔄 {msg}（タスク発行済み・対応待ち）")
                    else:
                        alerts.append(f"⚠️ {msg}")
                elif env.temperature < 18:
                    msg = f"[{zone_id}] 低温: {env.temperature:.1f}℃（基準: 18-26℃）"
                    if self._is_suppressed(zone_id, "low_temp"):
                        suppressed.append(f"🔄 {msg}（タスク発行済み・対応待ち）")
                    else:
                        alerts.append(f"⚠️ {msg}")
            if env.co2 is not None and env.co2 > 1000:
                msg = f"[{zone_id}] CO2高濃度: {env.co2}ppm（基準: 1000ppm以下）"
                if self._is_suppressed(zone_id, "high_co2"):
                    suppressed.append(f"🔄 {msg}（タスク発行済み・対応待ち）")
                else:
                    alerts.append(f"⚠️ {msg}")
            if env.humidity is not None:
                if env.humidity > 60:
                    msg = f"[{zone_id}] 高湿度: {env.humidity:.0f}%（基準: 30-60%）"
                    if self._is_suppressed(zone_id, "high_humidity"):
                        suppressed.append(f"🔄 {msg}（タスク発行済み・対応待ち）")
                    else:
                        alerts.append(f"⚠️ {msg}")
                elif env.humidity < 30:
                    msg = f"[{zone_id}] 低湿度: {env.humidity:.0f}%（基準: 30-60%）"
                    if self._is_suppressed(zone_id, "low_humidity"):
                        suppressed.append(f"🔄 {msg}（タスク発行済み・対応待ち）")
                    else:
                        alerts.append(f"⚠️ {msg}")

        if alerts:
            context_parts.append("### アラート（要対応）\n" + "\n".join(alerts))
        if suppressed:
            context_parts.append("### 対応中（タスク発行済み・新規タスク不要）\n" + "\n".join(suppressed))

        # Inventory status section
        if self.inventory_tracker:
            inv_items = self.inventory_tracker.get_inventory_status()
            low_items = [i for i in inv_items if i["status"] == "low"]
            if low_items:
                inv_lines = []
                for item in low_items:
                    suppressed_key = f"low_stock_{item['device_id']}"
                    if self._is_suppressed(item["zone"], suppressed_key):
                        inv_lines.append(
                            f"🔄 [{item['zone']}] {item['item_name']}: "
                            f"残量{item['quantity']}個（買い物リスト追加済み）"
                        )
                    else:
                        inv_lines.append(
                            f"⚠️ [{item['zone']}] {item['item_name']}: "
                            f"残量{item['quantity']}個（閾値: {item['min_threshold']}）"
                        )
                if inv_lines:
                    context_parts.append("### 在庫状況\n" + "\n".join(inv_lines))

        for zone_id, zone in sorted(self.zones.items()):
            summary = f"### {zone_id}\n"
            
            # Occupancy and activity
            if zone.occupancy.person_count > 0:
                summary += f"- 状態: {zone.occupancy.activity_summary}\n"
                if zone.occupancy.avg_motion_level > 0:
                    summary += f"- 活動レベル: {zone.occupancy.avg_motion_level:.2f}\n"
                if zone.occupancy.posture_status != "unknown":
                    minutes = int(zone.occupancy.posture_duration_sec / 60)
                    summary += f"- 姿勢状態: {zone.occupancy.posture_status} ({minutes}分間)\n"
            else:
                summary += "- 状態: 無人\n"
            
            # Environment
            if zone.environment.temperature is not None:
                summary += f"- 気温: {zone.environment.temperature:.1f}℃ ({zone.environment.thermal_comfort})\n"
            
            if zone.environment.humidity is not None:
                summary += f"- 湿度: {zone.environment.humidity:.0f}%\n"
            
            if zone.environment.co2 is not None:
                summary += f"- CO2: {zone.environment.co2}ppm"
                if zone.environment.is_stuffy:
                    summary += " ⚠️換気必要\n"
                else:
                    summary += "\n"
            
            if zone.environment.pressure is not None:
                summary += f"- 気圧: {zone.environment.pressure:.1f}hPa\n"

            if zone.environment.illuminance is not None:
                summary += f"- 照度: {zone.environment.illuminance:.0f}lux\n"
            
            # Devices
            if zone.devices:
                summary += "- デバイス:\n"
                for device_id, device in zone.devices.items():
                    summary += f"  - {device.device_type} ({device_id}): {device.power_state}\n"
            
            # Spatial summary
            if zone.spatial.persons and current_time - zone.spatial.last_spatial_update < 30:
                n_persons = len(zone.spatial.persons)
                # Summarize person distribution using image thirds
                if zone.spatial.image_size[0] > 0:
                    img_w = zone.spatial.image_size[0]
                    left = sum(1 for p in zone.spatial.persons if len(p.center_px) >= 1 and p.center_px[0] < img_w / 3)
                    center = sum(1 for p in zone.spatial.persons if len(p.center_px) >= 1 and img_w / 3 <= p.center_px[0] < 2 * img_w / 3)
                    right = n_persons - left - center
                    parts = []
                    if left > 0:
                        parts.append(f"左側{left}人")
                    if center > 0:
                        parts.append(f"中央{center}人")
                    if right > 0:
                        parts.append(f"右側{right}人")
                    if parts:
                        summary += f"- 配置: {', '.join(parts)}\n"

                # Object summary
                if zone.spatial.objects:
                    from collections import Counter
                    obj_counts = Counter(o.class_name for o in zone.spatial.objects)
                    obj_str = ", ".join(f"{name}x{cnt}" for name, cnt in obj_counts.most_common(5))
                    summary += f"- 検出物: {obj_str}\n"

            # Tracking summary (cross-camera person tracking)
            if zone.tracking.persons and current_time - zone.tracking.last_update < 30:
                summary += f"- 追跡中: {zone.tracking.person_count}人\n"
                for tp in zone.tracking.persons[:5]:  # Show up to 5 tracked persons
                    dur_min = int(tp.duration_sec / 60)
                    cams = ", ".join(tp.cameras) if tp.cameras else "?"
                    summary += (
                        f"  - ID#{tp.global_id}: "
                        f"({tp.floor_x_m:.1f}m, {tp.floor_y_m:.1f}m) "
                        f"{dur_min}分滞在 cameras=[{cams}]\n"
                    )

            # Adjacent zone occupancy
            if zone.metadata.adjacent_zones:
                adj_parts = []
                for adj_id in zone.metadata.adjacent_zones:
                    adj_zone = self.zones.get(adj_id)
                    if adj_zone and adj_zone.occupancy.person_count > 0:
                        adj_parts.append(f"{adj_id}({adj_zone.occupancy.person_count}人)")
                if adj_parts:
                    summary += f"- 隣接在室: {', '.join(adj_parts)}\n"

            # Recent events (last 10 minutes)
            recent_events = [
                e for e in zone.events
                if current_time - e.timestamp < 600
            ]
            if recent_events:
                summary += "- 最近のイベント:\n"
                for event in recent_events[-3:]:  # Last 3 events
                    summary += f"  - {event.description}\n"

            context_parts.append(summary)
        
        context = "\n".join(context_parts)
        
        # Update cache
        self._llm_context_cache = context
        self._cache_timestamp = current_time
        
        return context
