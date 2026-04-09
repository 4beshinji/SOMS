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

    # Minimum absolute tolerance (grams) for near-zero stability checks.
    # Load cell noise at near-zero is ~±2g; percentage tolerance alone
    # would require unrealistically tight readings.
    _MIN_STABLE_TOLERANCE_G: float = 5.0

    def _is_stable(self, readings: List[float]) -> bool:
        """Check if the last N readings are within tolerance of each other."""
        if len(readings) < self._stable_window:
            return False
        window = readings[-self._stable_window:]
        avg = sum(window) / len(window)
        # Use the larger of percentage-based and absolute minimum tolerance
        tolerance_g = max(
            abs(avg) * self._tolerance_pct / 100,
            self._MIN_STABLE_TOLERANCE_G,
        )
        return all(abs(v - avg) <= tolerance_g for v in window)

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
        """Get current inventory status for all tracked shelves.

        Shelves that have never received sensor data (current_weight_g is None)
        are excluded — they are config placeholders without a live sensor.
        """
        result = []
        for key, shelf in self._shelves.items():
            if zone and shelf.zone != zone:
                continue
            state = self._states[key]

            # Skip shelves with no sensor data received yet
            if state.current_weight_g is None:
                continue

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

    def get_registered_item_names(self) -> set:
        """Return set of item names for shelves with live sensor data.

        Shelves that have never received data are excluded so that
        config placeholders don't pollute the shopping whitelist.
        """
        return {
            shelf.item_name
            for key, shelf in self._shelves.items()
            if self._states[key].current_weight_g is not None
            and shelf.item_name  # skip null/empty names
        }

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

    def _match_single_item(
        self, weight_g: float, items: List[CompartmentItem],
        prefer_low_stock: bool = True,
        require_quantity: bool = True,
    ) -> Optional[tuple]:
        """Match a weight delta to a single item type.

        Returns (CompartmentItem, n_units) or None.
        Tolerance: ±30% of unit_weight.
        """
        if not items or weight_g <= 0:
            return None

        candidates = []
        for item in items:
            if item.unit_weight_g <= 0:
                continue
            if require_quantity and item.quantity <= 0:
                continue
            ratio = weight_g / item.unit_weight_g
            n_units = round(ratio)
            if require_quantity:
                n_units = min(n_units, item.quantity)
            if n_units >= 1:
                error_pct = (
                    abs(weight_g - n_units * item.unit_weight_g)
                    / item.unit_weight_g
                    * 100
                )
                if error_pct <= 30:
                    candidates.append((item, n_units, error_pct))

        if not candidates:
            return None

        if prefer_low_stock:
            candidates.sort(key=lambda x: (x[2], x[0].quantity))
        else:
            # For additions, prefer items with lowest stock (most likely restocked)
            candidates.sort(key=lambda x: (x[2], x[0].quantity))
        return candidates[0][0], candidates[0][1]

    def _match_combo(
        self, weight_g: float, items: List[CompartmentItem],
        require_quantity: bool = True,
    ) -> Optional[List[tuple]]:
        """Match a weight delta to a combination of 2 different item types.

        Returns [(CompartmentItem, n_units), ...] or None.
        Tolerance: ±20% (tighter than single-item to reduce false positives).
        """
        if len(items) < 2 or weight_g <= 0:
            return None

        eligible = [
            it for it in items
            if it.unit_weight_g > 0 and (not require_quantity or it.quantity > 0)
        ]
        if len(eligible) < 2:
            return None

        best = None
        best_error = float("inf")
        best_units = float("inf")

        for i in range(len(eligible)):
            for j in range(i + 1, len(eligible)):
                a, b = eligible[i], eligible[j]
                max_a = a.quantity if require_quantity else 5
                max_b = b.quantity if require_quantity else 5
                for na in range(1, min(max_a, 3) + 1):
                    for nb in range(1, min(max_b, 3) + 1):
                        combo_weight = na * a.unit_weight_g + nb * b.unit_weight_g
                        if combo_weight <= 0:
                            continue
                        error_pct = abs(weight_g - combo_weight) / combo_weight * 100
                        total_units = na + nb
                        if error_pct <= 20 and (
                            error_pct < best_error
                            or (error_pct == best_error and total_units < best_units)
                        ):
                            best = [(a, na), (b, nb)]
                            best_error = error_pct
                            best_units = total_units

        return best

    # Keep backward-compatible aliases
    def _estimate_consumed_item(self, weight_delta_g, items):
        return self._match_single_item(weight_delta_g, items)

    def _check_multi_item_consumption(
        self, key: str, state: ShelfState, shelf: ShelfConfig, stable_weight: float
    ) -> List[InventoryEvent]:
        """Check for item consumption or addition in multi-item mode.

        Returns a list of events (low_stock, restocked).
        """
        events = []
        now = time.time()

        if state.prev_total_weight_g is not None:
            delta = state.prev_total_weight_g - stable_weight

            if delta > self._MIN_STABLE_TOLERANCE_G:
                # Weight decreased — consumption
                self._handle_consumption(delta, state, shelf, events, now)

            elif delta < -self._MIN_STABLE_TOLERANCE_G:
                # Weight increased — item added / restocked
                increase = abs(delta)
                self._handle_addition(increase, state, shelf, events)

        state.prev_total_weight_g = stable_weight
        return events

    @staticmethod
    def _match_error(delta: float, result) -> float:
        """Calculate match error as percentage of delta."""
        if result is None:
            return float("inf")
        if isinstance(result, list):
            matched_weight = sum(n * item.unit_weight_g for item, n in result)
        else:
            matched_weight = result[1] * result[0].unit_weight_g
        return abs(delta - matched_weight) / delta * 100 if delta > 0 else float("inf")

    def _handle_consumption(
        self, delta: float, state: ShelfState, shelf: ShelfConfig,
        events: List[InventoryEvent], now: float,
    ):
        """Process weight decrease — pick best of single vs combo match."""
        single = self._match_single_item(delta, state.items)
        combo = self._match_combo(delta, state.items) if len(state.items) >= 2 else None

        single_err = self._match_error(delta, single)
        combo_err = self._match_error(delta, combo)

        if combo is not None and combo_err < single_err:
            for item, n_units in combo:
                self._apply_consumption(item, n_units, state, shelf, events, now)
        elif single is not None:
            self._apply_consumption(single[0], single[1], state, shelf, events, now)
        elif combo is not None:
            for item, n_units in combo:
                self._apply_consumption(item, n_units, state, shelf, events, now)
        else:
            logger.debug("Unmatched consumption: %.1fg delta", delta)

    def _apply_consumption(
        self, item: CompartmentItem, n_units: int,
        state: ShelfState, shelf: ShelfConfig,
        events: List[InventoryEvent], now: float,
    ):
        """Reduce item quantity and emit low_stock if needed."""
        item.quantity = max(0, item.quantity - n_units)
        item.total_weight_g = item.quantity * item.unit_weight_g
        logger.info(
            "Consumption: %s -%d (remaining: %d)",
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

    def _handle_addition(
        self, increase: float, state: ShelfState, shelf: ShelfConfig,
        events: List[InventoryEvent],
    ):
        """Process weight increase — pick best of single vs combo match."""
        single = self._match_single_item(
            increase, state.items, require_quantity=False,
        )
        combo = self._match_combo(
            increase, state.items, require_quantity=False,
        ) if len(state.items) >= 2 else None

        single_err = self._match_error(increase, single)
        combo_err = self._match_error(increase, combo)

        if combo is not None and combo_err < single_err:
            for item, n_units in combo:
                self._apply_addition(item, n_units, shelf, events)
        elif single is not None:
            self._apply_addition(single[0], single[1], shelf, events)
        elif combo is not None:
            for item, n_units in combo:
                self._apply_addition(item, n_units, shelf, events)
        else:
            logger.debug("Unmatched addition: %.1fg increase", increase)

    def _apply_addition(
        self, item: CompartmentItem, n_units: int,
        shelf: ShelfConfig, events: List[InventoryEvent],
    ):
        """Increase item quantity and emit restocked event."""
        item.quantity += n_units
        item.total_weight_g = item.quantity * item.unit_weight_g
        logger.info(
            "Addition: %s +%d (now: %d)",
            item.item_name, n_units, item.quantity,
        )
        events.append(InventoryEvent(
            event_type="restocked",
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

    def register_item(
        self,
        device_id: str,
        channel: str,
        item_name: str,
        unit_weight_g: float,
        quantity: int = 1,
        zone: str = None,
        **kwargs,
    ) -> Optional[InventoryEvent]:
        """Register an item on a shelf manually (no barcode required).

        Switches the shelf to multi-item mode and adds the item.
        If an item with the same name already exists, updates its quantity.
        """
        key = self._key(device_id, channel)
        state = self._states.get(key)
        shelf = self._shelves.get(key)

        if state is None:
            shelf = ShelfConfig(
                device_id=device_id,
                channel=channel,
                zone=zone or "unknown",
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

        if state.mode == "single":
            state.mode = "multi"

        # Check if item with same name already exists — update quantity
        for item in state.items:
            if item.item_name == item_name:
                item.quantity = quantity
                item.unit_weight_g = unit_weight_g
                item.total_weight_g = quantity * unit_weight_g
                logger.info(
                    "Item updated: %s quantity=%d (%.1fg each)",
                    item_name, quantity, unit_weight_g,
                )
                return InventoryEvent(
                    event_type="item_added",
                    zone=shelf.zone,
                    device_id=device_id,
                    channel=channel,
                    item_name=item_name,
                    category=item.category,
                    quantity=quantity,
                    min_threshold=item.min_threshold,
                    reorder_quantity=item.reorder_quantity,
                    store=item.store,
                    price=item.price,
                )

        # New item
        new_item = CompartmentItem(
            barcode=kwargs.get("barcode"),
            item_name=item_name,
            unit_weight_g=unit_weight_g,
            quantity=quantity,
            total_weight_g=quantity * unit_weight_g,
            min_threshold=kwargs.get("min_threshold", 1),
            reorder_quantity=kwargs.get("reorder_quantity", 1),
            category=kwargs.get("category", ""),
            store=kwargs.get("store"),
            price=kwargs.get("price"),
            last_scan_time=time.time(),
        )
        state.items.append(new_item)
        logger.info(
            "Item registered: %s x%d (%.1fg each) on %s",
            item_name, quantity, unit_weight_g, device_id,
        )

        return InventoryEvent(
            event_type="item_added",
            zone=shelf.zone,
            device_id=device_id,
            channel=channel,
            item_name=item_name,
            category=new_item.category,
            quantity=quantity,
            min_threshold=new_item.min_threshold,
            reorder_quantity=new_item.reorder_quantity,
            store=new_item.store,
            price=new_item.price,
        )

    def register_barcode(self, device_id: str, channel: str, barcode: str, weight_g: float = None):
        """Legacy stub — delegates to handle_barcode_scan."""
        self.handle_barcode_scan(device_id, channel, barcode, current_weight_g=weight_g)
