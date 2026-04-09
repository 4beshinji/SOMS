"""
Shelf scale node (XIAO ESP32-C6) — HX711 load cell weight monitoring.

Publishes weight readings to MQTT for inventory tracking.
Topic: office/{zone}/sensor/{device_id}/weight  {"value": 342.5}

MCP tools: get_status, tare, calibrate
"""
import machine
import time
import sys
import json

# Add shared library path
sys.path.insert(0, "/lib")

from soms_mcp import MCPDevice

# HX711 sensor instance (set during init)
_hx711 = None


def load_config():
    with open("config.json", "r") as f:
        return json.load(f)


def main():
    global _hx711
    cfg = load_config()

    device = MCPDevice()

    # Initialize HX711 via SensorRegistry
    from sensor_registry import SensorRegistry
    from board_pins import get_board_pins

    pins = get_board_pins(cfg.get("board", "xiao_esp32_c6"))
    registry = SensorRegistry(pins)

    for sensor_cfg in cfg.get("sensors", []):
        try:
            registry.add_sensor(sensor_cfg)
        except Exception as e:
            print(f"Sensor init error: {e}")

    # Get HX711 reference for calibration tools
    for name, driver in registry._sensors:
        if name == "hx711":
            _hx711 = driver
            # Try to load saved calibration
            if _hx711.load_calibration():
                print("Calibration loaded from NVS")
            break

    def get_status():
        return registry.read_all()

    def tare(readings=20):
        """Zero the scale with empty shelf."""
        if _hx711 is None:
            return {"status": "error", "message": "HX711 not initialized"}
        _hx711.tare(readings=readings)
        _hx711.save_calibration()
        cal = _hx711.get_calibration()
        return {"status": "ok", "offset": cal["offset"], "scale": cal["scale"]}

    def calibrate(known_weight_g, readings=10):
        """Set scale factor using known weight. Call tare() first with empty shelf."""
        if _hx711 is None:
            return {"status": "error", "message": "HX711 not initialized"}
        scale = _hx711.calibrate(known_weight_g, readings=readings)
        _hx711.save_calibration()
        cal = _hx711.get_calibration()
        return {"status": "ok", "scale": scale, "offset": cal["offset"]}

    device.register_tool("get_status", get_status)
    device.register_tool("tare", tare)
    device.register_tool("calibrate", calibrate)

    try:
        device.connect()
    except Exception:
        print("Connection failed, resetting...")
        machine.reset()

    last_report = 0

    while True:
        try:
            device.loop()

            now = time.time()
            if now - last_report > device.report_interval:
                try:
                    data = registry.read_all()
                    if data:
                        device.publish_sensor_data(data)
                    last_report = now
                except OSError:
                    print("Failed to read sensor")

            time.sleep(0.1)

        except OSError as e:
            print(f"Connection error: {e}")
            time.sleep(5)
            try:
                device.reconnect()
            except Exception:
                print("Reconnect failed, resetting...")
                time.sleep(10)
                machine.reset()
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
