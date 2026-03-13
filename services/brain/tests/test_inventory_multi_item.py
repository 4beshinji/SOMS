"""Unit tests for InventoryTracker multi-item (barcode hybrid) mode."""
import time
import pytest

from inventory_tracker import (
    InventoryTracker, ShelfConfig, ShelfState, CompartmentItem,
    InventoryEvent,
)


def _make_tracker_with_shelf(device_id="shelf_01", zone="kitchen", **kwargs):
    """Create a tracker with one configured shelf for testing."""
    tracker = InventoryTracker.__new__(InventoryTracker)
    tracker._shelves = {}
    tracker._states = {}
    tracker._stable_window = 3
    tracker._tolerance_pct = 5.0
    tracker._cooldown_sec = 3600.0

    shelf = ShelfConfig(
        device_id=device_id,
        channel="weight",
        zone=zone,
        item_name=kwargs.get("item_name", "test item"),
        category=kwargs.get("category", "general"),
        unit_weight_g=kwargs.get("unit_weight_g", 200.0),
        tare_weight_g=kwargs.get("tare_weight_g", 50.0),
        min_threshold=kwargs.get("min_threshold", 2),
        reorder_quantity=kwargs.get("reorder_quantity", 1),
    )
    key = f"{device_id}:weight"
    tracker._shelves[key] = shelf
    tracker._states[key] = ShelfState()
    return tracker


class TestBarcodeScanning:
    """Barcode scan → item addition."""

    def test_barcode_scan_creates_item(self):
        tracker = _make_tracker_with_shelf()
        event = tracker.handle_barcode_scan(
            "shelf_01", "weight", "4901234567890",
            item_name="コーヒー豆", unit_weight_g=200.0,
        )
        assert event is not None
        assert event.event_type == "item_added"
        assert event.item_name == "コーヒー豆"

        state = tracker._states["shelf_01:weight"]
        assert state.mode == "multi"
        assert len(state.items) == 1
        assert state.items[0].barcode == "4901234567890"

    def test_barcode_rescan_increments_quantity(self):
        tracker = _make_tracker_with_shelf()
        tracker.handle_barcode_scan(
            "shelf_01", "weight", "4901234567890",
            item_name="コーヒー豆", unit_weight_g=200.0,
        )
        event = tracker.handle_barcode_scan(
            "shelf_01", "weight", "4901234567890",
        )
        assert event.event_type == "item_added"
        state = tracker._states["shelf_01:weight"]
        assert state.items[0].quantity == 2

    def test_barcode_scan_unknown_shelf_creates_entry(self):
        tracker = InventoryTracker.__new__(InventoryTracker)
        tracker._shelves = {}
        tracker._states = {}
        tracker._stable_window = 3
        tracker._tolerance_pct = 5.0
        tracker._cooldown_sec = 3600.0

        event = tracker.handle_barcode_scan(
            "unknown_shelf", "weight", "1234567890",
            item_name="Unknown Item",
        )
        assert event is not None
        assert "unknown_shelf:weight" in tracker._states
        assert tracker._states["unknown_shelf:weight"].mode == "multi"

    def test_barcode_default_name_uses_barcode(self):
        tracker = _make_tracker_with_shelf()
        tracker.handle_barcode_scan("shelf_01", "weight", "9999999")
        state = tracker._states["shelf_01:weight"]
        assert state.items[0].item_name == "barcode:9999999"

    def test_multiple_different_items(self):
        tracker = _make_tracker_with_shelf()
        tracker.handle_barcode_scan(
            "shelf_01", "weight", "111", item_name="ItemA", unit_weight_g=100.0,
        )
        tracker.handle_barcode_scan(
            "shelf_01", "weight", "222", item_name="ItemB", unit_weight_g=300.0,
        )
        state = tracker._states["shelf_01:weight"]
        assert len(state.items) == 2
        assert state.items[0].item_name == "ItemA"
        assert state.items[1].item_name == "ItemB"


class TestConsumptionEstimation:
    """Weight decrease → consumed item estimation."""

    def test_estimate_single_match(self):
        tracker = _make_tracker_with_shelf()
        items = [
            CompartmentItem(barcode="A", item_name="A", unit_weight_g=200.0,
                           quantity=5, total_weight_g=1000.0),
        ]
        result = tracker._estimate_consumed_item(200.0, items)
        assert result is not None
        item, n_units = result
        assert item.item_name == "A"
        assert n_units == 1

    def test_estimate_two_units(self):
        tracker = _make_tracker_with_shelf()
        items = [
            CompartmentItem(barcode="A", item_name="A", unit_weight_g=100.0,
                           quantity=5, total_weight_g=500.0),
        ]
        result = tracker._estimate_consumed_item(200.0, items)
        assert result is not None
        _, n_units = result
        assert n_units == 2

    def test_estimate_within_tolerance(self):
        tracker = _make_tracker_with_shelf()
        items = [
            CompartmentItem(barcode="A", item_name="A", unit_weight_g=200.0,
                           quantity=5, total_weight_g=1000.0),
        ]
        # 220g is within ±30% of 200g → should match
        result = tracker._estimate_consumed_item(220.0, items)
        assert result is not None

    def test_estimate_outside_tolerance(self):
        tracker = _make_tracker_with_shelf()
        items = [
            CompartmentItem(barcode="A", item_name="A", unit_weight_g=200.0,
                           quantity=5, total_weight_g=1000.0),
        ]
        # 320g is >30% of 200 but round(320/200)=2, error = |320-400|/200 = 40% > 30%
        result = tracker._estimate_consumed_item(320.0, items)
        assert result is None

    def test_estimate_prefers_low_stock(self):
        tracker = _make_tracker_with_shelf()
        items = [
            CompartmentItem(barcode="A", item_name="A", unit_weight_g=200.0,
                           quantity=10, total_weight_g=2000.0),
            CompartmentItem(barcode="B", item_name="B", unit_weight_g=200.0,
                           quantity=2, total_weight_g=400.0),
        ]
        result = tracker._estimate_consumed_item(200.0, items)
        assert result is not None
        item, _ = result
        assert item.item_name == "B"  # lower stock preferred

    def test_estimate_zero_quantity_skipped(self):
        tracker = _make_tracker_with_shelf()
        items = [
            CompartmentItem(barcode="A", item_name="A", unit_weight_g=200.0,
                           quantity=0, total_weight_g=0.0),
        ]
        result = tracker._estimate_consumed_item(200.0, items)
        assert result is None

    def test_estimate_negative_delta(self):
        tracker = _make_tracker_with_shelf()
        items = [
            CompartmentItem(barcode="A", item_name="A", unit_weight_g=200.0,
                           quantity=5, total_weight_g=1000.0),
        ]
        result = tracker._estimate_consumed_item(-50.0, items)
        assert result is None


class TestMultiItemWeightUpdate:
    """Weight updates in multi-item mode."""

    def _setup_multi_shelf(self):
        tracker = _make_tracker_with_shelf()
        state = tracker._states["shelf_01:weight"]
        state.mode = "multi"
        state.items = [
            CompartmentItem(barcode="A", item_name="ItemA", unit_weight_g=200.0,
                           quantity=5, total_weight_g=1000.0, min_threshold=2),
        ]
        return tracker

    def _feed_stable(self, tracker, weight, n=3):
        """Feed N stable readings and return last event."""
        event = None
        for _ in range(n):
            event = tracker.update_weight("kitchen", "shelf_01", "weight", weight)
        return event

    def test_multi_mode_consumption_detected(self):
        tracker = self._setup_multi_shelf()
        state = tracker._states["shelf_01:weight"]

        # Initial stable weight
        state.prev_total_weight_g = 1050.0
        event = self._feed_stable(tracker, 850.0)  # 200g drop → 1 unit consumed
        assert state.items[0].quantity == 4

    def test_multi_mode_low_stock_event(self):
        tracker = self._setup_multi_shelf()
        state = tracker._states["shelf_01:weight"]
        state.items[0].quantity = 2
        state.items[0].min_threshold = 2

        state.prev_total_weight_g = 500.0
        event = self._feed_stable(tracker, 300.0)  # 200g drop → quantity 2→1
        assert event is not None
        assert event.event_type == "low_stock"
        assert event.item_name == "ItemA"

    def test_multi_mode_no_event_when_stable(self):
        tracker = self._setup_multi_shelf()
        state = tracker._states["shelf_01:weight"]
        state.prev_total_weight_g = 1050.0
        event = self._feed_stable(tracker, 1050.0)  # No change
        assert event is None


class TestModeTransition:
    """Single → multi mode transition."""

    def test_single_to_multi_on_barcode_scan(self):
        tracker = _make_tracker_with_shelf()
        state = tracker._states["shelf_01:weight"]
        assert state.mode == "single"

        tracker.handle_barcode_scan("shelf_01", "weight", "1234", item_name="Test")
        assert state.mode == "multi"

    def test_single_mode_weight_update_unchanged(self):
        """Verify single-mode logic still works normally."""
        tracker = _make_tracker_with_shelf(unit_weight_g=200.0, tare_weight_g=50.0)
        # Feed 3 stable readings at 450g → (450-50)/200 = 2 items
        for _ in range(3):
            tracker.update_weight("kitchen", "shelf_01", "weight", 450.0)
        state = tracker._states["shelf_01:weight"]
        assert state.mode == "single"
        assert state.quantity == 2


class TestInventoryStatusMultiItem:
    """get_inventory_status with multi-item shelves."""

    def test_multi_item_reports_individual_items(self):
        tracker = _make_tracker_with_shelf()
        state = tracker._states["shelf_01:weight"]
        state.mode = "multi"
        state.items = [
            CompartmentItem(barcode="A", item_name="ItemA", unit_weight_g=200.0,
                           quantity=5, total_weight_g=1000.0, category="cat1"),
            CompartmentItem(barcode="B", item_name="ItemB", unit_weight_g=100.0,
                           quantity=1, total_weight_g=100.0, min_threshold=2, category="cat2"),
        ]

        status = tracker.get_inventory_status()
        assert len(status) == 2
        assert status[0]["item_name"] == "ItemA"
        assert status[0]["status"] == "ok"
        assert status[0]["mode"] == "multi"
        assert status[1]["item_name"] == "ItemB"
        assert status[1]["status"] == "low"
        assert status[1]["barcode"] == "B"
