"""
InventoryTracker — weight-based consumable inventory monitoring.

Tracks shelf sensor weights, calculates item quantities, and emits
low_stock events when inventory drops below configured thresholds.

Phase 2 stub: register_barcode() for hybrid weight+barcode tracking.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ShelfConfig:
    device_id: str
    channel: str
    zone: str
    item_name: str
    category: str
    unit_weight_g: float
    tare_weight_g: float
    min_threshold: int
    reorder_quantity: int
    store: Optional[str] = None
    price: Optional[float] = None
    barcode: Optional[str] = None


@dataclass
class CompartmentItem:
    """Individual item on a multi-item shelf."""
    barcode: Optional[str]
    item_name: str
    unit_weight_g: float
    quantity: int
    total_weight_g: float  # quantity * unit_weight_g
    min_threshold: int = 1
    reorder_quantity: int = 1
    category: str = ""
    store: Optional[str] = None
    price: Optional[float] = None
    last_scan_time: float = 0.0


@dataclass
class ShelfState:
    """Runtime state — supports single and multi-item modes."""
    current_weight_g: Optional[float] = None
    quantity: int = 0
    readings: List[float] = field(default_factory=list)
    last_low_stock_time: float = 0.0
    prev_quantity: Optional[int] = None
    # Multi-item mode
    items: List[CompartmentItem] = field(default_factory=list)
    mode: str = "single"  # "single" | "multi"
    prev_total_weight_g: Optional[float] = None


@dataclass
class InventoryEvent:
    """Event emitted when inventory state changes."""
    event_type: str  # "low_stock" | "restocked"
    zone: str
    device_id: str
    channel: str
    item_name: str
    category: str
    quantity: int
    min_threshold: int
    reorder_quantity: int
    store: Optional[str] = None
    price: Optional[float] = None


class InventoryTracker:
    """
    Core inventory tracking logic.

    Receives weight sensor updates, calculates item quantities via
    tare subtraction and unit weight division, detects low stock
    with stable-reading filtering and cooldown.
    """

    def __init__(self, config_path: str = "config/inventory.yaml"):
        self._shelves: Dict[str, ShelfConfig] = {}   # key: "device_id:channel"
        self._states: Dict[str, ShelfState] = {}
        self._stable_window: int = 3
        self._tolerance_pct: float = 5.0
        self._cooldown_sec: float = 3600.0
        self._load_config(config_path)

    def _load_config(self, path: str):
        """Load inventory configuration from YAML."""
        try:
            with open(path, "r") as f:
                raw = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("Inventory config not found: %s", path)
            return
        except Exception as e:
            logger.error("Failed to load inventory config: %s", e)
            return

        settings = raw.get("settings", {})
        self._stable_window = settings.get("stable_reading_window", 3)
        self._tolerance_pct = settings.get("weight_tolerance_pct", 5.0)
        self._cooldown_sec = settings.get("low_stock_cooldown_sec", 3600.0)

        for entry in raw.get("shelves", []):
            shelf = ShelfConfig(
                device_id=entry["device_id"],
                channel=entry.get("channel", "weight"),
                zone=entry["zone"],
                item_name=entry["item_name"],
                category=entry.get("category", ""),
                unit_weight_g=entry["unit_weight_g"],
                tare_weight_g=entry.get("tare_weight_g", 0.0),
                min_threshold=entry.get("min_threshold", 1),
                reorder_quantity=entry.get("reorder_quantity", 1),
                store=entry.get("store"),
                price=entry.get("price"),
                barcode=entry.get("barcode"),
            )
            key = f"{shelf.device_id}:{shelf.channel}"
            self._shelves[key] = shelf
            self._states[key] = ShelfState()

        logger.info("Inventory config loaded: %d shelves", len(self._shelves))

    def load_from_api_data(self, items: List[Dict[str, Any]]):
        """Load shelf configurations from Inventory API response data.

        Merges API items with any existing YAML-loaded config.
        API items take precedence over YAML for the same device_id:channel.
        """
        count = 0
        for entry in items:
            shelf = ShelfConfig(
                device_id=entry["device_id"],
                channel=entry.get("channel", "weight"),
                zone=entry["zone"],
                item_name=entry["item_name"],
                category=entry.get("category", ""),
                unit_weight_g=entry["unit_weight_g"],
                tare_weight_g=entry.get("tare_weight_g", 0.0),
                min_threshold=entry.get("min_threshold", 1),
                reorder_quantity=entry.get("reorder_quantity", 1),
                store=entry.get("store"),
                price=entry.get("price"),
                barcode=entry.get("barcode"),
            )
            key = f"{shelf.device_id}:{shelf.channel}"
            self._shelves[key] = shelf
            if key not in self._states:
                self._states[key] = ShelfState()
            count += 1

        logger.info("Inventory items loaded from API: %d items", count)

    def _key(self, device_id: str, channel: str) -> str:
        return f"{device_id}:{channel}"

    def _calculate_quantity(self, weight_g: float, shelf: ShelfConfig) -> int:
        """Calculate item count from weight, accounting for tare."""
        net = weight_g - shelf.tare_weight_g
        if net <= 0 or shelf.unit_weight_g <= 0:
            return 0
        return int(net / shelf.unit_weight_g)

    def _is_stable(self, readings: List[float]) -> bool:
        """Check if the last N readings are within tolerance of each other."""
        if len(readings) < self._stable_window:
            return False
        window = readings[-self._stable_window:]
        avg = sum(window) / len(window)
        if avg == 0:
            return all(v == 0 for v in window)
        return all(
            abs(v - avg) / abs(avg) * 100 <= self._tolerance_pct
            for v in window
        )

    def update_weight(
        self, zone: str, device_id: str, channel: str, weight_g: float
    ) -> Optional[InventoryEvent]:
        """
        Process a weight sensor reading.

        Returns an InventoryEvent if a low_stock or restocked condition
        is detected, None otherwise. For multi-item shelves, returns the
        first low_stock event (if any).
        """
        key = self._key(device_id, channel)
        shelf = self._shelves.get(key)
        if shelf is None:
            return None  # Not a tracked shelf sensor

        if shelf.zone != zone:
            return None  # Zone mismatch

        state = self._states[key]
        state.readings.append(weight_g)

        # Keep readings buffer bounded
        if len(state.readings) > self._stable_window * 3:
            state.readings = state.readings[-self._stable_window * 3:]

        # Wait for stable readings
        if not self._is_stable(state.readings):
            return None

        # Stable reading
        stable_weight = sum(state.readings[-self._stable_window:]) / self._stable_window
        state.current_weight_g = stable_weight

        # Multi-item mode — delegate to multi-item consumption logic
        if state.mode == "multi":
            events = self._check_multi_item_consumption(key, state, shelf, stable_weight)
            return events[0] if events else None

        # Single-item mode
        quantity = self._calculate_quantity(stable_weight, shelf)
        state.quantity = quantity

        now = time.time()

        # Detect restocking (quantity increased)
        if state.prev_quantity is not None and quantity > state.prev_quantity:
            state.prev_quantity = quantity
            state.last_low_stock_time = 0.0  # Reset cooldown on restock
            logger.info(
                "Restock detected: %s quantity %d→%d",
                shelf.item_name, state.prev_quantity, quantity,
            )
            return InventoryEvent(
                event_type="restocked",
                zone=shelf.zone,
                device_id=device_id,
                channel=channel,
                item_name=shelf.item_name,
                category=shelf.category,
                quantity=quantity,
                min_threshold=shelf.min_threshold,
                reorder_quantity=shelf.reorder_quantity,
                store=shelf.store,
                price=shelf.price,
            )

        state.prev_quantity = quantity

        # Check low stock with cooldown
        if quantity < shelf.min_threshold:
            if now - state.last_low_stock_time >= self._cooldown_sec:
                state.last_low_stock_time = now
                logger.info(
                    "Low stock: %s quantity=%d (threshold=%d)",
                    shelf.item_name, quantity, shelf.min_threshold,
                )
                return InventoryEvent(
                    event_type="low_stock",
                    zone=shelf.zone,
                    device_id=device_id,
                    channel=channel,
                    item_name=shelf.item_name,
                    category=shelf.category,
                    quantity=quantity,
                    min_threshold=shelf.min_threshold,
                    reorder_quantity=shelf.reorder_quantity,
                    store=shelf.store,
                    price=shelf.price,
                )

        return None

    def get_inventory_status(self, zone: str = None) -> List[Dict[str, Any]]:
        """Get current inventory status for all tracked shelves."""
        result = []
        for key, shelf in self._shelves.items():
            if zone and shelf.zone != zone:
                continue
            state = self._states[key]

            if state.mode == "multi" and state.items:
                # Multi-item mode: report each item individually
                for item in state.items:
                    result.append({
                        "device_id": shelf.device_id,
                        "channel": shelf.channel,
                        "zone": shelf.zone,
                        "item_name": item.item_name,
                        "category": item.category,
                        "quantity": item.quantity,
                        "min_threshold": item.min_threshold,
                        "current_weight_g": state.current_weight_g,
                        "status": "low" if item.quantity < item.min_threshold else "ok",
                        "mode": "multi",
                        "barcode": item.barcode,
                    })
            else:
                # Single-item mode
                result.append({
                    "device_id": shelf.device_id,
                    "channel": shelf.channel,
                    "zone": shelf.zone,
                    "item_name": shelf.item_name,
                    "category": shelf.category,
                    "quantity": state.quantity,
                    "min_threshold": shelf.min_threshold,
                    "current_weight_g": state.current_weight_g,
                    "status": "low" if state.quantity < shelf.min_threshold else "ok",
                })
        return result

    def get_item_for_shopping(self, device_id: str, channel: str) -> Optional[Dict[str, Any]]:
        """Get shopping item data for a shelf sensor (for Shopping API)."""
        key = self._key(device_id, channel)
        shelf = self._shelves.get(key)
        if shelf is None:
            return None
        state = self._states[key]
        return {
            "name": shelf.item_name,
            "category": shelf.category,
            "quantity": shelf.reorder_quantity,
            "store": shelf.store,
            "price": shelf.price,
            "notes": f"在庫残量: {state.quantity}個 (自動検知)",
            "priority": 2,
            "created_by": "inventory_tracker",
        }

    def is_tracked_sensor(self, device_id: str, channel: str) -> bool:
        """Check if a device_id:channel combination is a tracked shelf sensor."""
        return self._key(device_id, channel) in self._shelves

    def lookup_barcode(self, barcode: str) -> Optional[Dict[str, Any]]:
        """Look up a barcode in registered shelf configs.

        Returns item metadata if a matching barcode is found, None otherwise.
        """
        for shelf in self._shelves.values():
            if shelf.barcode and shelf.barcode == barcode:
                return {
                    "item_name": shelf.item_name,
                    "unit_weight_g": shelf.unit_weight_g,
                    "category": shelf.category,
                    "store": shelf.store,
                    "price": shelf.price,
                    "min_threshold": shelf.min_threshold,
                    "reorder_quantity": shelf.reorder_quantity,
                }
        return None

    def handle_barcode_scan(
        self,
        device_id: str,
        channel: str,
        barcode: str,
        item_name: str = None,
        unit_weight_g: float = None,
        current_weight_g: float = None,
    ) -> Optional[InventoryEvent]:
        """Handle barcode scan — add or update item on a multi-item shelf.

        If the shelf is in single mode, it transitions to multi mode.
        Returns an InventoryEvent("item_added") on success.
        """
        key = self._key(device_id, channel)
        state = self._states.get(key)
        shelf = self._shelves.get(key)

        if state is None:
            # Unknown shelf — create a minimal shelf entry for multi-item tracking
            shelf = ShelfConfig(
                device_id=device_id,
                channel=channel,
                zone="unknown",
                item_name="multi-item shelf",
                category="",
                unit_weight_g=0,
                tare_weight_g=0,
                min_threshold=1,
                reorder_quantity=1,
            )
            self._shelves[key] = shelf
            state = ShelfState(mode="multi")
            self._states[key] = state

        # Switch to multi mode on first barcode scan
        if state.mode == "single":
            state.mode = "multi"

        # Resolve item metadata from DB/YAML if not provided
        if item_name is None or unit_weight_g is None:
            known = self.lookup_barcode(barcode)
            if known:
                item_name = item_name or known["item_name"]
                unit_weight_g = unit_weight_g if unit_weight_g is not None else known["unit_weight_g"]
                logger.info("Barcode %s resolved to: %s (%.1fg)", barcode, item_name, unit_weight_g)

        name = item_name or f"barcode:{barcode}"
        weight = unit_weight_g or 0.0

        # Check if this barcode already exists — update quantity
        for item in state.items:
            if item.barcode == barcode:
                item.quantity += 1
                item.total_weight_g = item.quantity * item.unit_weight_g
                item.last_scan_time = time.time()
                logger.info(
                    "Barcode rescan: %s quantity→%d", item.item_name, item.quantity
                )
                return InventoryEvent(
                    event_type="item_added",
                    zone=shelf.zone,
                    device_id=device_id,
                    channel=channel,
                    item_name=item.item_name,
                    category=item.category,
                    quantity=item.quantity,
                    min_threshold=item.min_threshold,
                    reorder_quantity=item.reorder_quantity,
                    store=item.store,
                    price=item.price,
                )

        # New item — enrich with lookup data if available
        known = self.lookup_barcode(barcode) or {}
        new_item = CompartmentItem(
            barcode=barcode,
            item_name=name,
            unit_weight_g=weight,
            quantity=1,
            total_weight_g=weight,
            min_threshold=known.get("min_threshold", 1),
            reorder_quantity=known.get("reorder_quantity", 1),
            category=known.get("category", ""),
            store=known.get("store"),
            price=known.get("price"),
            last_scan_time=time.time(),
        )
        state.items.append(new_item)
        logger.info("New item added via barcode: %s (%sg)", name, weight)

        return InventoryEvent(
            event_type="item_added",
            zone=shelf.zone,
            device_id=device_id,
            channel=channel,
            item_name=name,
            category=new_item.category,
            quantity=1,
            min_threshold=new_item.min_threshold,
            reorder_quantity=new_item.reorder_quantity,
            store=new_item.store,
            price=new_item.price,
        )

    def _estimate_consumed_item(
        self, weight_delta_g: float, items: List[CompartmentItem]
    ) -> Optional[tuple]:
        """Estimate which item was consumed based on weight decrease.

        Returns (CompartmentItem, n_units) or None.
        Strategy:
        1. Find items whose unit_weight matches weight_delta within ±30%
        2. Among candidates, prefer the one with lowest stock (most likely consumed)
        """
        if not items or weight_delta_g <= 0:
            return None

        candidates = []
        for item in items:
            if item.quantity <= 0 or item.unit_weight_g <= 0:
                continue
            ratio = weight_delta_g / item.unit_weight_g
            n_units = round(ratio)
            if n_units >= 1:
                error_pct = (
                    abs(weight_delta_g - n_units * item.unit_weight_g)
                    / item.unit_weight_g
                    * 100
                )
                if error_pct <= 30:
                    candidates.append((item, n_units, error_pct))

        if not candidates:
            return None

        # Sort by error, then by quantity ascending (low stock first)
        candidates.sort(key=lambda x: (x[2], x[0].quantity))
        return candidates[0][0], candidates[0][1]

    def _check_multi_item_consumption(
        self, key: str, state: ShelfState, shelf: ShelfConfig, stable_weight: float
    ) -> List[InventoryEvent]:
        """Check for item consumption in multi-item mode.

        Returns a list of events (low_stock for any items below threshold).
        """
        events = []
        now = time.time()

        if state.prev_total_weight_g is not None:
            delta = state.prev_total_weight_g - stable_weight
            if delta > 0:
                # Weight decreased — something was consumed
                result = self._estimate_consumed_item(delta, state.items)
                if result:
                    item, n_units = result
                    item.quantity = max(0, item.quantity - n_units)
                    item.total_weight_g = item.quantity * item.unit_weight_g
                    logger.info(
                        "Consumption detected: %s -%d (remaining: %d)",
                        item.item_name, n_units, item.quantity,
                    )

                    if item.quantity < item.min_threshold:
                        if now - state.last_low_stock_time >= self._cooldown_sec:
                            state.last_low_stock_time = now
                            events.append(InventoryEvent(
                                event_type="low_stock",
                                zone=shelf.zone,
                                device_id=shelf.device_id,
                                channel=shelf.channel,
                                item_name=item.item_name,
                                category=item.category,
                                quantity=item.quantity,
                                min_threshold=item.min_threshold,
                                reorder_quantity=item.reorder_quantity,
                                store=item.store,
                                price=item.price,
                            ))

        state.prev_total_weight_g = stable_weight
        return events

    def register_barcode(self, device_id: str, channel: str, barcode: str, weight_g: float = None):
        """Legacy stub — delegates to handle_barcode_scan."""
        self.handle_barcode_scan(device_id, channel, barcode, current_weight_g=weight_g)
