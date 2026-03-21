"""
SOMS Unified Sensor Node — config-driven firmware for any ESP32 + sensor combo.

Reads config.json to determine board type and sensor configuration,
then initializes only the sensors that are physically present.
Missing or failing sensors are gracefully skipped.

Compatible with Tier 1 (DHT22 only) through Tier 4 (multi-zone).
"""

import time
import machine
import sys

# Add shared library path
sys.path.insert(0, "/edge_lib")

from soms_mcp import MCPDevice
from board_pins import get_board_pins
from sensor_registry import SensorRegistry

# ---- Initialize device ----

device = MCPDevice()
board_name = device.config.get("board", "esp32_devkitc")
pins = get_board_pins(board_name)
print(f"Board: {board_name}, pins: {pins}")

# ---- Initialize sensors from config ----

registry = SensorRegistry(pins)
sensor_configs = device.config.get("sensors", [])

for scfg in sensor_configs:
    try:
        registry.add_sensor(scfg)
    except Exception as e:
        print(f"Skipping sensor {scfg.get('type', '?')}: {e}")

print(f"Active sensors: {registry.sensor_names} ({registry.sensor_count}/{len(sensor_configs)})")

# ---- Disable ABC on MH-Z19C (manual calibration only) ----

mhz19 = registry.get_driver("mhz19c")
if mhz19:
    mhz19.set_abc(False)

# ---- LED (optional) ----

led = None
if pins.get("led", -1) >= 0:
    try:
        led = machine.Pin(pins["led"], machine.Pin.OUT)
    except Exception:
        pass

# ---- MCP Tools ----

def get_status():
    data = registry.read_all()
    data["uptime_ms"] = time.ticks_diff(time.ticks_ms(), device._boot_ticks)
    data["board"] = board_name
    data["active_sensors"] = registry.sensor_names
    return data


def restart():
    print("Restart requested via MCP")
    time.sleep(1)
    machine.reset()


def co2_calibrate():
    """Zero-point calibration. Device must be in fresh outdoor air for 20+ min."""
    mhz = registry.get_driver("mhz19c")
    if mhz is None:
        return {"error": "mhz19c not active"}
    mhz.zero_calibrate()
    return {"result": "zero-point calibration executed"}


def co2_set_abc(enabled=False):
    """Enable or disable ABC (Automatic Baseline Correction)."""
    mhz = registry.get_driver("mhz19c")
    if mhz is None:
        return {"error": "mhz19c not active"}
    mhz.set_abc(enabled)
    return {"result": f"ABC {'ON' if enabled else 'OFF'}"}


device.register_tool("get_status", get_status)
device.register_tool("restart", restart)
device.register_tool("co2_calibrate", co2_calibrate)
device.register_tool("co2_set_abc", co2_set_abc)

# ---- Connect & main loop ----

device.connect()
print("Unified node running — reporting every %ds" % device.report_interval)

while True:
    try:
        device.loop()

        data = registry.read_all()
        if data:
            device.publish_sensor_data(data)
            if led:
                led.on()
                time.sleep_ms(50)
                led.off()

        time.sleep(device.report_interval)

    except OSError as e:
        print(f"Connection error: {e}")
        time.sleep(5)
        try:
            device.reconnect()
        except Exception:
            print("Reconnect failed, resetting in 10s...")
            time.sleep(10)
            machine.reset()
