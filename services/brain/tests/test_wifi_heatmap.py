"""Tests for WiFi-CSI heatmap integration in WorldModel."""
import time

import pytest

from world_model.world_model import WorldModel
from world_model.data_classes import ZoneMetadata


def _make_world_model_with_zone(zone_id="office", polygon=None, grid_rows=4, grid_cols=4):
    """Create a WorldModel with one zone that has polygon metadata and heatmap grid."""
    wm = WorldModel()
    if polygon is None:
        # Simple 10m x 10m square zone
        polygon = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]

    wm.update_from_mqtt(f"office/{zone_id}/sensor/env_01/temperature", {"value": 22.0})
    zone = wm.zones[zone_id]
    zone.metadata = ZoneMetadata(
        display_name="Test Zone",
        polygon=polygon,
        area_m2=100.0,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
    )
    zone.spatial.heatmap_counts = [[0] * grid_cols for _ in range(grid_rows)]
    zone.spatial.heatmap_window_start = time.time()
    return wm


class TestAccumulateHeatmapFromFloorCoords:
    """Tests for _accumulate_heatmap_from_floor_coords."""

    def test_basic_accumulation(self):
        wm = _make_world_model_with_zone()
        zone = wm.zones["office"]

        # Person at centre of 10x10m zone → grid cell (2, 2) in 4x4 grid
        wm._accumulate_heatmap_from_floor_coords(
            zone, [(5.0, 5.0)], time.time()
        )
        assert zone.spatial.heatmap_counts[2][2] == 1

    def test_corner_positions(self):
        wm = _make_world_model_with_zone()
        zone = wm.zones["office"]
        now = time.time()

        # Top-left corner (0, 0) → grid (0, 0)
        wm._accumulate_heatmap_from_floor_coords(zone, [(0.1, 0.1)], now)
        assert zone.spatial.heatmap_counts[0][0] == 1

        # Bottom-right corner (9.9, 9.9) → grid (3, 3)
        wm._accumulate_heatmap_from_floor_coords(zone, [(9.9, 9.9)], now)
        assert zone.spatial.heatmap_counts[3][3] == 1

    def test_multiple_persons_same_cell(self):
        wm = _make_world_model_with_zone()
        zone = wm.zones["office"]
        now = time.time()

        wm._accumulate_heatmap_from_floor_coords(
            zone, [(5.0, 5.0), (5.1, 5.1), (5.2, 5.2)], now
        )
        assert zone.spatial.heatmap_counts[2][2] == 3

    def test_positions_outside_zone_skipped(self):
        wm = _make_world_model_with_zone()
        zone = wm.zones["office"]
        now = time.time()

        # Way outside the zone polygon
        wm._accumulate_heatmap_from_floor_coords(
            zone, [(-5.0, -5.0), (20.0, 20.0)], now
        )
        total = sum(sum(row) for row in zone.spatial.heatmap_counts)
        assert total == 0

    def test_no_polygon_no_crash(self):
        wm = _make_world_model_with_zone()
        zone = wm.zones["office"]
        zone.metadata.polygon = []

        # Should silently return
        wm._accumulate_heatmap_from_floor_coords(
            zone, [(5.0, 5.0)], time.time()
        )
        total = sum(sum(row) for row in zone.spatial.heatmap_counts)
        assert total == 0

    def test_hourly_reset(self):
        wm = _make_world_model_with_zone()
        zone = wm.zones["office"]

        # Accumulate some data
        old_time = time.time() - 3700  # > 1 hour ago
        zone.spatial.heatmap_window_start = old_time
        zone.spatial.heatmap_counts[1][1] = 99

        # Next accumulation should reset
        wm._accumulate_heatmap_from_floor_coords(
            zone, [(5.0, 5.0)], time.time()
        )
        # Old data (99) should be gone; only the new point remains
        assert zone.spatial.heatmap_counts[1][1] == 0
        assert zone.spatial.heatmap_counts[2][2] == 1

    def test_real_zone_polygon(self):
        """Use an actual zone polygon from spatial.yaml (zone_01)."""
        polygon = [[23.13, 9.34], [23.13, 11.57], [25.54, 11.57], [25.54, 9.16]]
        wm = _make_world_model_with_zone(
            zone_id="zone_01", polygon=polygon, grid_rows=2, grid_cols=2
        )
        zone = wm.zones["zone_01"]

        # Centre of this zone: ~24.3, ~10.4
        wm._accumulate_heatmap_from_floor_coords(
            zone, [(24.3, 10.4)], time.time()
        )
        total = sum(sum(row) for row in zone.spatial.heatmap_counts)
        assert total == 1


class TestUpdateWifiPose:
    """Tests for wifi-pose MQTT routing and heatmap accumulation."""

    def test_wifi_pose_routed(self):
        """wifi-pose topic should be handled by WorldModel."""
        wm = _make_world_model_with_zone()
        zone = wm.zones["office"]
        zone.tracking.last_update = 0  # Tracking is stale

        wm.update_from_mqtt(
            "office/office/wifi-pose/wifi_01",
            {"persons": [{"id": 1, "x": 5.0, "y": 5.0, "confidence": 0.7}]},
        )
        total = sum(sum(row) for row in zone.spatial.heatmap_counts)
        assert total == 1

    def test_wifi_pose_skipped_when_tracking_active(self):
        """When tracking is fresh, wifi-pose should not double-accumulate."""
        wm = _make_world_model_with_zone()
        zone = wm.zones["office"]
        zone.tracking.last_update = time.time()  # Tracking is fresh

        wm.update_from_mqtt(
            "office/office/wifi-pose/wifi_01",
            {"persons": [{"id": 1, "x": 5.0, "y": 5.0, "confidence": 0.7}]},
        )
        total = sum(sum(row) for row in zone.spatial.heatmap_counts)
        assert total == 0

    def test_wifi_pose_empty_persons(self):
        wm = _make_world_model_with_zone()
        zone = wm.zones["office"]
        zone.tracking.last_update = 0

        wm.update_from_mqtt(
            "office/office/wifi-pose/wifi_01",
            {"persons": []},
        )
        total = sum(sum(row) for row in zone.spatial.heatmap_counts)
        assert total == 0

    def test_wifi_pose_records_event_store(self):
        """Event store should receive WiFi spatial snapshot."""
        wm = _make_world_model_with_zone()
        zone = wm.zones["office"]
        zone.tracking.last_update = 0

        from unittest.mock import MagicMock
        wm.event_writer = MagicMock()

        wm.update_from_mqtt(
            "office/office/wifi-pose/wifi_01",
            {"persons": [{"id": 1, "x": 5.0, "y": 5.0, "confidence": 0.7}]},
        )
        wm.event_writer.record_spatial_snapshot.assert_called_once()
        call_kwargs = wm.event_writer.record_spatial_snapshot.call_args
        assert call_kwargs[1]["camera_id"] == "wifi:wifi_01"
        assert call_kwargs[1]["data"]["source"] == "wifi-csi"


class TestTrackingHeatmapIntegration:
    """Tests for heatmap accumulation from cross-camera tracking."""

    def test_tracking_accumulates_heatmap(self):
        wm = _make_world_model_with_zone()

        wm.update_from_mqtt(
            "office/office/tracking",
            {
                "person_count": 1,
                "persons": [
                    {
                        "global_id": 1,
                        "floor_x_m": 5.0,
                        "floor_y_m": 5.0,
                        "zone": "office",
                        "cameras": ["cam_01"],
                        "confidence": 0.9,
                        "duration_sec": 60.0,
                    }
                ],
            },
        )
        zone = wm.zones["office"]
        total = sum(sum(row) for row in zone.spatial.heatmap_counts)
        assert total == 1

    def test_tracking_skips_zero_coords(self):
        """Persons with (0, 0) floor coords should be skipped."""
        wm = _make_world_model_with_zone()

        wm.update_from_mqtt(
            "office/office/tracking",
            {
                "person_count": 1,
                "persons": [
                    {
                        "global_id": 1,
                        "floor_x_m": 0.0,
                        "floor_y_m": 0.0,
                        "zone": "office",
                        "cameras": [],
                        "confidence": 0.5,
                        "duration_sec": 10.0,
                    }
                ],
            },
        )
        zone = wm.zones["office"]
        total = sum(sum(row) for row in zone.spatial.heatmap_counts)
        assert total == 0

    def test_tracking_multiple_persons_different_cells(self):
        wm = _make_world_model_with_zone()

        wm.update_from_mqtt(
            "office/office/tracking",
            {
                "person_count": 2,
                "persons": [
                    {
                        "global_id": 1,
                        "floor_x_m": 1.0,
                        "floor_y_m": 1.0,
                        "zone": "office",
                        "cameras": ["cam_01"],
                        "confidence": 0.9,
                        "duration_sec": 60.0,
                    },
                    {
                        "global_id": 2,
                        "floor_x_m": 8.0,
                        "floor_y_m": 8.0,
                        "zone": "office",
                        "cameras": ["cam_02"],
                        "confidence": 0.9,
                        "duration_sec": 30.0,
                    },
                ],
            },
        )
        zone = wm.zones["office"]
        total = sum(sum(row) for row in zone.spatial.heatmap_counts)
        assert total == 2
        # They should be in different cells
        assert zone.spatial.heatmap_counts[0][0] == 1  # (1,1) → grid (0,0)
        assert zone.spatial.heatmap_counts[3][3] == 1  # (8,8) → grid (3,3)
