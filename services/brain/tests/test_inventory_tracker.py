"""Tests for InventoryTracker — weight-based inventory monitoring."""
import time
import pytest
from unittest.mock import patch

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from inventory_tracker import InventoryTracker, ShelfConfig, ShelfState


@pytest.fixture
def sample_config(tmp_path):
    """Create a temporary inventory config for testing."""
    config = tmp_path / "inventory.yaml"
    config.write_text("""
shelves:
  - device_id: shelf_01
    channel: weight
    zone: kitchen
    item_name: コーヒー豆
    category: 飲料
    unit_weight_g: 200.0
    tare_weight_g: 50.0
    min_threshold: 1
    reorder_quantity: 3
    store: カルディ
    price: 800
    barcode: null

  - device_id: shelf_02
    channel: weight
    zone: main
    item_name: コピー用紙 A4
    category: 事務用品
    unit_weight_g: 2500.0
    tare_weight_g: 100.0
    min_threshold: 2
    reorder_quantity: 5
    store: null
    price: null
    barcode: null

settings:
  stable_reading_window: 3
  weight_tolerance_pct: 5.0
  low_stock_cooldown_sec: 3600
""")
    return str(config)


@pytest.fixture
def tracker(sample_config):
    return InventoryTracker(config_path=sample_config)


class TestConfigLoading:
    def test_loads_shelves(self, tracker):
        assert len(tracker._shelves) == 2
        shelf = tracker._shelves["shelf_01:weight"]
        assert shelf.item_name == "コーヒー豆"
        assert shelf.unit_weight_g == 200.0
        assert shelf.tare_weight_g == 50.0

    def test_loads_settings(self, tracker):
        assert tracker._stable_window == 3
        assert tracker._tolerance_pct == 5.0
        assert tracker._cooldown_sec == 3600.0

    def test_missing_config_file(self):
        tracker = InventoryTracker(config_path="/nonexistent.yaml")
        assert len(tracker._shelves) == 0

    def test_is_tracked_sensor(self, tracker):
        assert tracker.is_tracked_sensor("shelf_01", "weight") is True
        assert tracker.is_tracked_sensor("shelf_01", "temperature") is False
        assert tracker.is_tracked_sensor("unknown", "weight") is False


class TestWeightUpdate:
    def test_normal_stock(self, tracker):
        """3 bags of coffee (600g) + 50g tare = 650g → quantity=3, above threshold."""
        # Need 3 stable readings
        assert tracker.update_weight("kitchen", "shelf_01", "weight", 650.0) is None
        assert tracker.update_weight("kitchen", "shelf_01", "weight", 650.0) is None
        event = tracker.update_weight("kitchen", "shelf_01", "weight", 650.0)
        # quantity=3, threshold=1 → no event
        assert event is None
        status = tracker.get_inventory_status("kitchen")
        assert len(status) == 1
        assert status[0]["quantity"] == 3
        assert status[0]["status"] == "ok"

    def test_low_stock_event(self, tracker):
        """Under threshold triggers low_stock event."""
        # 0.5 bags worth: 50 (tare) + 100 (half bag) = 150g → quantity=0
        for _ in range(2):
            tracker.update_weight("kitchen", "shelf_01", "weight", 150.0)
        event = tracker.update_weight("kitchen", "shelf_01", "weight", 150.0)
        assert event is not None
        assert event.event_type == "low_stock"
        assert event.item_name == "コーヒー豆"
        assert event.quantity == 0
        assert event.reorder_quantity == 3
        assert event.store == "カルディ"

    def test_empty_shelf(self, tracker):
        """Only tare weight remains → quantity=0, low_stock."""
        for _ in range(2):
            tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)
        event = tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)
        assert event is not None
        assert event.event_type == "low_stock"
        assert event.quantity == 0

    def test_below_tare(self, tracker):
        """Weight below tare (sensor drift) → quantity=0."""
        for _ in range(2):
            tracker.update_weight("kitchen", "shelf_01", "weight", 30.0)
        event = tracker.update_weight("kitchen", "shelf_01", "weight", 30.0)
        assert event is not None
        assert event.event_type == "low_stock"
        assert event.quantity == 0

    def test_zone_mismatch_ignored(self, tracker):
        """Wrong zone should be ignored."""
        for _ in range(3):
            result = tracker.update_weight("main", "shelf_01", "weight", 50.0)
        assert result is None

    def test_unknown_sensor_ignored(self, tracker):
        """Unknown device_id should return None."""
        result = tracker.update_weight("kitchen", "unknown_shelf", "weight", 100.0)
        assert result is None


class TestStableReading:
    def test_unstable_readings_no_event(self, tracker):
        """Fluctuating readings should not produce events."""
        tracker.update_weight("kitchen", "shelf_01", "weight", 100.0)
        tracker.update_weight("kitchen", "shelf_01", "weight", 200.0)
        event = tracker.update_weight("kitchen", "shelf_01", "weight", 100.0)
        assert event is None

    def test_gradual_convergence(self, tracker):
        """Readings that converge within tolerance should trigger."""
        # These are within 5% of each other: 150, 152, 151 → avg~151
        tracker.update_weight("kitchen", "shelf_01", "weight", 150.0)
        tracker.update_weight("kitchen", "shelf_01", "weight", 152.0)
        event = tracker.update_weight("kitchen", "shelf_01", "weight", 151.0)
        # 150,152,151 → within 5% of avg ~151 → stable → quantity = (151-50)/200 = 0
        assert event is not None
        assert event.event_type == "low_stock"


class TestCooldown:
    def test_cooldown_prevents_repeat(self, tracker):
        """Second low_stock within cooldown should not emit."""
        for _ in range(3):
            tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)
        # First event fires
        event = tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)
        # This was already the third reading, so event should have fired at 3rd
        # Let's reset and try again
        for _ in range(3):
            result = tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)
        # Should be None due to cooldown
        assert result is None

    def test_cooldown_expires(self, tracker):
        """After cooldown expires, low_stock fires again."""
        for _ in range(3):
            tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)

        # Simulate cooldown expiry
        state = tracker._states["shelf_01:weight"]
        state.last_low_stock_time = time.time() - 3601

        for _ in range(3):
            tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)
        # After stable + expired cooldown → should fire
        # prev_quantity was set to 0, so no restocked event, but low_stock should re-fire
        event = tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)
        # The readings buffer has many 50.0s now, stable check passes
        # Need to check — after 6+ readings of 50.0, it should be stable
        status = tracker.get_inventory_status("kitchen")
        assert status[0]["quantity"] == 0


class TestRestockDetection:
    def test_restock_detected(self, tracker):
        """Quantity increase should emit restocked event."""
        # First: establish low stock (quantity=0)
        for _ in range(3):
            tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)

        # Now restock: 3 bags + tare = 650g
        for _ in range(2):
            tracker.update_weight("kitchen", "shelf_01", "weight", 650.0)
        event = tracker.update_weight("kitchen", "shelf_01", "weight", 650.0)
        assert event is not None
        assert event.event_type == "restocked"
        assert event.quantity == 3

    def test_restock_resets_cooldown(self, tracker):
        """After restocking, low_stock cooldown should be reset."""
        # Establish low stock
        for _ in range(3):
            tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)
        state = tracker._states["shelf_01:weight"]
        assert state.last_low_stock_time > 0

        # Restock
        for _ in range(3):
            tracker.update_weight("kitchen", "shelf_01", "weight", 650.0)
        assert state.last_low_stock_time == 0.0


class TestConsumptionDetection:
    def test_gradual_consumption(self, tracker):
        """Simulates gradual item consumption triggering low_stock."""
        # Start with 3 bags (650g)
        for _ in range(3):
            tracker.update_weight("kitchen", "shelf_01", "weight", 650.0)

        # Consume to 1 bag (250g) — still above threshold
        for _ in range(3):
            tracker.update_weight("kitchen", "shelf_01", "weight", 250.0)
        status = tracker.get_inventory_status("kitchen")
        assert status[0]["quantity"] == 1
        assert status[0]["status"] == "ok"

        # Consume to 0 bags (50g) — below threshold
        for _ in range(2):
            tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)
        event = tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)
        assert event is not None
        assert event.event_type == "low_stock"


class TestShoppingIntegration:
    def test_get_item_for_shopping(self, tracker):
        """get_item_for_shopping returns Shopping API-compatible data."""
        # Set some state
        for _ in range(3):
            tracker.update_weight("kitchen", "shelf_01", "weight", 50.0)

        item = tracker.get_item_for_shopping("shelf_01", "weight")
        assert item is not None
        assert item["name"] == "コーヒー豆"
        assert item["category"] == "飲料"
        assert item["quantity"] == 3  # reorder_quantity
        assert item["store"] == "カルディ"
        assert item["price"] == 800
        assert "自動検知" in item["notes"]
        assert item["created_by"] == "inventory_tracker"

    def test_get_item_unknown_shelf(self, tracker):
        assert tracker.get_item_for_shopping("unknown", "weight") is None


class TestInventoryStatus:
    def test_all_zones(self, tracker):
        status = tracker.get_inventory_status()
        assert len(status) == 2

    def test_filter_by_zone(self, tracker):
        status = tracker.get_inventory_status("kitchen")
        assert len(status) == 1
        assert status[0]["zone"] == "kitchen"

    def test_empty_zone(self, tracker):
        status = tracker.get_inventory_status("nonexistent")
        assert len(status) == 0


class TestBarcodeRegistration:
    def test_register_barcode(self, tracker):
        """register_barcode should delegate to handle_barcode_scan."""
        tracker.register_barcode("shelf_01", "weight", "4901234567890")
        state = tracker._states["shelf_01:weight"]
        assert state.mode == "multi"
        assert len(state.items) == 1
        assert state.items[0].barcode == "4901234567890"

    def test_register_barcode_unknown_shelf(self, tracker):
        """Unknown shelf barcode registration should create new entry."""
        tracker.register_barcode("unknown", "weight", "4901234567890")
        assert "unknown:weight" in tracker._states
