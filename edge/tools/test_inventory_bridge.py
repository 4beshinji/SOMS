"""
USB-serial bridge: reads HX711 weight from XIAO ESP32-C6 via mpremote,
feeds values into InventoryTracker to test the full inventory logic.

Usage:
    .venv/bin/python edge/tools/test_inventory_bridge.py [--port /dev/ttyACM0] [--interval 3]
"""
import argparse
import subprocess
import sys
import time
import os

# Force unbuffered output
os.environ["PYTHONUNBUFFERED"] = "1"

sys.path.insert(0, "services/brain/src")
from inventory_tracker import InventoryTracker


READ_SCRIPT = """
from lib.drivers.hx711_driver import HX711
import time
hx = HX711(22, 23)
time.sleep_ms(200)
try: hx._read_raw()
except: pass
time.sleep_ms(200)
hx.load_calibration()
w = hx.read_weight(5)
print(round(w, 1))
"""


def read_weight(mpremote: str, port: str) -> float | None:
    """Read one weight value from device via mpremote exec."""
    try:
        result = subprocess.run(
            [mpremote, "connect", port, "exec", READ_SCRIPT],
            capture_output=True, text=True, timeout=15,
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            try:
                return float(line)
            except ValueError:
                continue
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"  [error] {e}")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--mpremote", default=".venv/bin/mpremote")
    args = parser.parse_args()

    tracker = InventoryTracker("config/inventory.yaml")
    print("=== Inventory Bridge Test ===")
    print(f"Port: {args.port}  Interval: {args.interval}s")
    print(f"Shelves loaded: {len(tracker._shelves)}")
    for key, shelf in tracker._shelves.items():
        print(f"  {key}: {shelf.item_name} (unit={shelf.unit_weight_g}g, threshold={shelf.min_threshold})")
    print()
    print("Reading weight from scale_01... (Ctrl+C to stop)")
    print("-" * 60)

    cycle = 0
    try:
        while True:
            weight = read_weight(args.mpremote, args.port)
            cycle += 1

            if weight is None:
                print(f"[{cycle}] read failed")
                time.sleep(args.interval)
                continue

            # Feed into InventoryTracker
            event = tracker.update_weight(
                zone="kitchen",
                device_id="scale_01",
                channel="weight",
                weight_g=weight,
            )

            # Get current status
            status = tracker.get_inventory_status()
            scale_status = [s for s in status if s["device_id"] == "scale_01"]

            if scale_status:
                s = scale_status[0]
                status_icon = "⚠️" if s["status"] == "low" else "✅"
                print(
                    f"[{cycle}] {weight:7.1f}g → "
                    f"qty={s['quantity']} {status_icon} "
                    f"({s['item_name']})"
                )
            else:
                print(f"[{cycle}] {weight:7.1f}g → (stabilizing...)")

            if event:
                print(f"  >>> EVENT: {event.event_type} — {event.item_name} qty={event.quantity}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n\nFinal status:")
        for s in tracker.get_inventory_status():
            print(f"  {s['item_name']}: qty={s['quantity']} ({s['current_weight_g']:.1f}g) [{s['status']}]")


if __name__ == "__main__":
    main()
