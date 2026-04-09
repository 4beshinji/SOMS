"""
MQTT inventory tracker: subscribes to weight telemetry, tracks items,
and accepts manual item registration.

Usage:
    # Monitor only
    .venv/bin/python edge/tools/test_inventory_mqtt.py

    # Register an item and start monitoring
    .venv/bin/python edge/tools/test_inventory_mqtt.py \
        --register scale_01 "中公新書" 193.8 --quantity 1
"""
import argparse
import json
import os
import sys
import time

os.environ["PYTHONUNBUFFERED"] = "1"
sys.path.insert(0, "services/brain/src")

import paho.mqtt.client as mqtt
from inventory_tracker import InventoryTracker

REGISTER_TOPIC = "soms/inventory/register"


def _flush():
    sys.stdout.flush()


def monitor(args):
    """Subscribe to weight telemetry, run InventoryTracker."""
    tracker = InventoryTracker("config/inventory.yaml")

    # Register item directly if requested (before MQTT loop)
    if args.register:
        event = tracker.register_item(
            device_id=args.register,
            channel=args.channel,
            item_name=args.item_name,
            unit_weight_g=args.unit_weight_g,
            quantity=args.quantity,
        )
        print(f"+++ Registered: {args.item_name} ({args.unit_weight_g}g x{args.quantity}) on {args.register}")
        if event:
            print(f"    event: {event.event_type}")

    print("=== MQTT Inventory Monitor ===")
    print(f"Broker: {args.broker}:{args.port}")
    for key, shelf in tracker._shelves.items():
        state = tracker._states[key]
        mode_tag = f" [{state.mode}]" if state.mode == "multi" else ""
        print(f"  {key}: {shelf.item_name} (unit={shelf.unit_weight_g}g){mode_tag}")
        if state.mode == "multi" and state.items:
            for item in state.items:
                print(f"    -> {item.item_name}: {item.unit_weight_g}g x{item.quantity}")
    print("-" * 65)
    _flush()

    cycle = [0]

    def on_message(client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            return

        # Handle live registration via MQTT
        if topic == REGISTER_TOPIC:
            event = tracker.register_item(
                device_id=payload["device_id"],
                channel=payload.get("channel", "weight"),
                item_name=payload["item_name"],
                unit_weight_g=payload["unit_weight_g"],
                quantity=payload.get("quantity", 1),
                zone=payload.get("zone"),
            )
            print(f"+++ REGISTERED: {payload['item_name']} "
                  f"({payload['unit_weight_g']}g x{payload.get('quantity', 1)})")
            _flush()
            return

        # Handle weight telemetry: office/{zone}/sensor/{device_id}/weight
        parts = topic.split("/")
        if len(parts) == 5 and parts[4] == "weight":
            zone = parts[1]
            device_id = parts[3]
            weight = payload.get("value")
            if weight is None:
                return

            cycle[0] += 1
            event = tracker.update_weight(zone, device_id, "weight", weight)

            status = tracker.get_inventory_status()
            dev_status = [s for s in status if s["device_id"] == device_id]

            if dev_status:
                parts_str = []
                for s in dev_status:
                    icon = "\u26a0\ufe0f" if s["status"] == "low" else "\u2705"
                    mode = f"[{s.get('mode', 'single')}]" if s.get("mode") == "multi" else ""
                    parts_str.append(
                        f"{s['item_name']}: qty={s['quantity']} {icon} {mode}"
                    )
                print(f"[{cycle[0]:3d}] {weight:7.1f}g | {' | '.join(parts_str)}")
            else:
                print(f"[{cycle[0]:3d}] {weight:7.1f}g | (stabilizing...)")

            if event:
                print(f"  >>> {event.event_type}: {event.item_name} qty={event.quantity}")
            _flush()

    def on_connect(client, userdata, flags, rc, properties=None):
        print(f"MQTT connected (rc={rc})")
        client.subscribe("office/+/sensor/+/weight")
        client.subscribe(REGISTER_TOPIC)
        _flush()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="inventory-test")
    client.username_pw_set(args.user, args.password)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.broker, args.port)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\nFinal status:")
        for s in tracker.get_inventory_status():
            mode = f" [{s.get('mode', 'single')}]" if s.get("mode") == "multi" else ""
            print(f"  {s['item_name']}: qty={s['quantity']} ({s['current_weight_g']:.1f}g) [{s['status']}]{mode}")
        client.disconnect()


def main():
    parser = argparse.ArgumentParser(description="MQTT Inventory Tracker Test Tool")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--user", default="soms")
    parser.add_argument("--password", default="soms_dev_mqtt")
    parser.add_argument("--channel", default="weight")

    # Register + monitor
    parser.add_argument("--register", metavar="DEVICE_ID",
                        help="Register an item on DEVICE_ID before monitoring")
    parser.add_argument("item_name", nargs="?", help="Item name")
    parser.add_argument("unit_weight_g", nargs="?", type=float, help="Unit weight (grams)")
    parser.add_argument("--quantity", type=int, default=1)

    args = parser.parse_args()

    if args.register and (not args.item_name or not args.unit_weight_g):
        parser.error("--register requires item_name and unit_weight_g")

    monitor(args)


if __name__ == "__main__":
    main()
