#!/usr/bin/env bash
# Flash and deploy shelf-scale-c6 firmware to XIAO ESP32-C6.
#
# Usage:
#   ./flash.sh              # auto-detect port
#   ./flash.sh /dev/ttyACM0 # explicit port
#   ./flash.sh --libs-only  # skip MicroPython flash, upload libs+app only
#
# Prerequisites:
#   uv pip install esptool mpremote --python .venv/bin/python

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
EDGE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LIB_DIR="$EDGE_DIR/lib"
FIRMWARE="$EDGE_DIR/office/sensor-02/firmware/ESP32_GENERIC_C6-latest.bin"
VENV="$REPO_DIR/.venv/bin"

# Resolve tool paths (venv or system)
ESPTOOL="${ESPTOOL:-$(command -v esptool 2>/dev/null || echo "$VENV/esptool")}"
MPREMOTE="${MPREMOTE:-$(command -v mpremote 2>/dev/null || echo "$VENV/mpremote")}"

LIBS_ONLY=false
PORT=""

for arg in "$@"; do
  case "$arg" in
    --libs-only) LIBS_ONLY=true ;;
    *) PORT="$arg" ;;
  esac
done

# --- Auto-detect port ---
if [ -z "$PORT" ]; then
  for p in /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB0 /dev/ttyUSB1; do
    if [ -e "$p" ]; then
      PORT="$p"
      break
    fi
  done
  if [ -z "$PORT" ]; then
    echo "ERROR: No serial port found. Connect the XIAO ESP32-C6 and retry."
    exit 1
  fi
fi

echo "=== SOMS Shelf Scale C6 — Flash Tool ==="
echo "Port: $PORT"
echo ""

# --- Step 1: Flash MicroPython firmware ---
if [ "$LIBS_ONLY" = false ]; then
  if [ ! -f "$FIRMWARE" ]; then
    echo "ERROR: MicroPython firmware not found at:"
    echo "  $FIRMWARE"
    echo "Download ESP32_GENERIC_C6 from https://micropython.org/download/ESP32_GENERIC_C6/"
    exit 1
  fi

  echo "[1/3] Erasing flash..."
  "$ESPTOOL" --port "$PORT" erase_flash

  echo ""
  echo "[2/3] Writing MicroPython firmware..."
  "$ESPTOOL" --port "$PORT" --baud 460800 write_flash 0x0 "$FIRMWARE"

  echo ""
  echo "Waiting for device reboot..."
  sleep 3
else
  echo "[1/3] Skipped (--libs-only)"
  echo "[2/3] Skipped (--libs-only)"
fi

# --- Step 2: Upload libraries and application ---
echo ""
echo "[3/3] Uploading files..."

MPR="$MPREMOTE connect $PORT"

# Create directory structure
$MPR fs mkdir :lib 2>/dev/null || true
$MPR fs mkdir :lib/drivers 2>/dev/null || true

# Core libraries
echo "  lib/soms_mcp.py"
$MPR fs cp "$LIB_DIR/soms_mcp.py" :lib/soms_mcp.py

echo "  lib/sensor_registry.py"
$MPR fs cp "$LIB_DIR/sensor_registry.py" :lib/sensor_registry.py

echo "  lib/board_pins.py"
$MPR fs cp "$LIB_DIR/board_pins.py" :lib/board_pins.py

# HX711 driver only (minimal set for weight-only test)
echo "  lib/drivers/hx711_driver.py"
$MPR fs cp "$LIB_DIR/drivers/hx711_driver.py" :lib/drivers/hx711_driver.py

# Application
echo "  config.json"
$MPR fs cp "$SCRIPT_DIR/config.json" :config.json

echo "  main.py"
$MPR fs cp "$SCRIPT_DIR/main.py" :main.py

echo ""
echo "=== Done ==="
echo ""
echo "Next steps:"
echo "  1. Edit config.json with your WiFi/MQTT settings before flashing,"
echo "     or update on-device:"
echo "     $MPREMOTE connect $PORT edit :config.json"
echo ""
echo "  2. Reset to start:"
echo "     $MPREMOTE connect $PORT reset"
echo ""
echo "  3. Monitor serial output:"
echo "     $MPREMOTE connect $PORT"
echo ""
echo "  4. Calibrate (REPL):"
echo "     >>> from lib.drivers.hx711_driver import HX711"
echo "     >>> hx = HX711(2, 3)"
echo "     >>> hx.is_ready()          # should be True"
echo "     >>> hx.tare(20)            # empty scale"
echo "     >>> # place 500g weight"
echo "     >>> hx.calibrate(500, 10)  # returns scale factor"
echo "     >>> hx.save_calibration()"
