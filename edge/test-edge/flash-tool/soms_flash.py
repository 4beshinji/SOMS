#!/usr/bin/env python3
"""
SOMS ESP32 Auto-Flash Tool

Detects USB-connected ESP32 devices, reads their MAC address,
looks up configuration in fleet.yaml, generates firmware config,
builds with PlatformIO, flashes, and verifies boot.

Usage:
    soms_flash.py watch                    # USB watch daemon mode
    soms_flash.py flash /dev/ttyUSB0       # Flash single device
    soms_flash.py list                     # List registered devices
    soms_flash.py identify /dev/ttyUSB0    # Read MAC + detect type only
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import serial
import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EDGE_DIR = Path(__file__).resolve().parent.parent  # edge/test-edge/
FLASH_TOOL_DIR = Path(__file__).resolve().parent
FLEET_FILE = FLASH_TOOL_DIR / "fleet.yaml"

# USB VID:PID -> (chip, default device type)
USB_DEVICE_MAP: dict[tuple[int, int], tuple[str, str]] = {
    (0x10C4, 0xEA60): ("CP2102 (ESP32 WROVER)", "camera"),
    (0x1A86, 0x7523): ("CH340 (ESP32)", "camera"),
    (0x303A, 0x1001): ("ESP32-S3 native USB", "sensor"),
}

# PlatformIO project dirs per device type
FW_DIRS: dict[str, Path] = {
    "camera": EDGE_DIR / "camera-node",
    "sensor": EDGE_DIR / "sensor-node",
}

# Serial boot markers
BOOT_MARKERS: dict[str, str] = {
    "camera": "=== Ready ===",
    "sensor": "=== Initialization Complete ===",
}

INTERMEDIATE_MARKERS: dict[str, list[str]] = {
    "camera": ["Camera initialized", "WiFi connected", "MQTT connected"],
    "sensor": ["BME680 initialized", "WiFi connected", "MQTT connected"],
}

SERIAL_TIMEOUT = 30  # seconds

def _find_tool(name: str) -> Optional[str]:
    """Find a CLI tool by name, checking PATH and the project venv."""
    found = shutil.which(name)
    if found:
        return found
    venv_bin = Path(__file__).resolve().parent.parent.parent.parent / ".venv" / "bin"
    candidate = venv_bin / name
    if candidate.exists():
        return str(candidate)
    return None
MQTT_VERIFY_TIMEOUT = 60  # seconds

# Lock per firmware type to prevent concurrent PlatformIO builds
_build_locks: dict[str, threading.Lock] = {
    "camera": threading.Lock(),
    "sensor": threading.Lock(),
}

log = logging.getLogger("soms_flash")


# ---------------------------------------------------------------------------
# Fleet config
# ---------------------------------------------------------------------------

def expand_env(value: str) -> str:
    """Expand ${VAR} references in string values."""
    def _replace(m: re.Match) -> str:
        return os.environ.get(m.group(1), "")
    if isinstance(value, str):
        return re.sub(r"\$\{(\w+)\}", _replace, value)
    return value


def load_fleet() -> dict:
    """Load fleet.yaml, expanding env vars in string values."""
    if not FLEET_FILE.exists():
        log.error("fleet.yaml not found at %s", FLEET_FILE)
        log.error("Copy fleet.yaml.example to fleet.yaml and configure it.")
        sys.exit(1)

    with open(FLEET_FILE) as f:
        raw = yaml.safe_load(f) or {}

    def _walk(obj):
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(v) for v in obj]
        if isinstance(obj, str):
            return expand_env(obj)
        return obj

    return _walk(raw)


def save_fleet(fleet: dict) -> None:
    """Write fleet.yaml back to disk (preserves new device entries)."""
    with open(FLEET_FILE, "w") as f:
        yaml.dump(fleet, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    log.info("Updated fleet.yaml")


def get_device_config(fleet: dict, mac: str, dev_type: str) -> dict:
    """Look up or auto-assign a device config for the given MAC."""
    mac_upper = mac.upper()
    if fleet.get("devices") is None:
        fleet["devices"] = {}
    devices = fleet["devices"]

    if mac_upper in devices:
        cfg = devices[mac_upper]
        cfg.setdefault("type", dev_type)
        return cfg

    # Auto-assign
    auto = fleet.get("auto_assign", {}).get(dev_type, {})
    prefix = auto.get("id_prefix", f"{dev_type}_node_")
    zone = auto.get("zone", "main")

    # Find next index
    existing_ids = [
        d.get("device_id", "") for d in devices.values()
        if d.get("type") == dev_type
    ]
    idx = 1
    while f"{prefix}{idx:02d}" in existing_ids:
        idx += 1
    device_id = f"{prefix}{idx:02d}"

    cfg = {"device_id": device_id, "zone": zone, "type": dev_type}
    devices[mac_upper] = cfg
    save_fleet(fleet)
    log.info("Auto-assigned %s -> %s (zone=%s)", mac_upper, device_id, zone)
    return cfg


# ---------------------------------------------------------------------------
# MAC address reading via esptool
# ---------------------------------------------------------------------------

def read_mac(port: str) -> Optional[str]:
    """Read MAC address from ESP32 via esptool."""
    # Try 'esptool' first (v5+), fall back to 'esptool.py' (legacy)
    esptool_path = _find_tool("esptool") or _find_tool("esptool.py")
    if not esptool_path:
        log.error("esptool not found. Install with: uv pip install esptool")
        return None

    try:
        result = subprocess.run(
            [esptool_path, "--port", port, "read-mac"],
            capture_output=True, text=True, timeout=15,
        )
        # Parse MAC from output like "MAC: aa:bb:cc:dd:ee:ff"
        combined = result.stdout + result.stderr
        for line in combined.splitlines():
            m = re.search(r"MAC:\s*([0-9a-fA-F:]{17})", line)
            if m:
                return m.group(1).upper()
        log.error("Could not parse MAC from esptool output:\n%s", combined)
        return None
    except subprocess.TimeoutExpired:
        log.error("esptool timed out on %s", port)
        return None
    except Exception as e:
        log.error("esptool error on %s: %s", port, e)
        return None


# ---------------------------------------------------------------------------
# Device type detection from USB VID:PID
# ---------------------------------------------------------------------------

def detect_device_type_from_usb(port: str) -> Optional[str]:
    """Detect device type from USB VID:PID via sysfs."""
    # Try to find the USB device info from sysfs
    port_name = Path(port).name  # e.g. ttyUSB0 or ttyACM0
    sysfs_base = Path(f"/sys/class/tty/{port_name}/device")

    if not sysfs_base.exists():
        return None

    # Walk up to find the USB device with idVendor/idProduct
    current = sysfs_base.resolve()
    for _ in range(10):
        vid_path = current / "idVendor"
        pid_path = current / "idProduct"
        if vid_path.exists() and pid_path.exists():
            try:
                vid = int(vid_path.read_text().strip(), 16)
                pid = int(pid_path.read_text().strip(), 16)
                key = (vid, pid)
                if key in USB_DEVICE_MAP:
                    chip, dev_type = USB_DEVICE_MAP[key]
                    log.info("USB %04x:%04x -> %s (type=%s)", vid, pid, chip, dev_type)
                    return dev_type
                log.warning("Unknown USB %04x:%04x on %s", vid, pid, port)
                return None
            except ValueError:
                pass
        current = current.parent
        if current == Path("/"):
            break

    return None


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------

def generate_config_h(fleet: dict, device_cfg: dict, fw_dir: Path) -> Path:
    """Generate generated_config.h in the firmware src/ directory."""
    defaults = fleet.get("defaults", {})
    src_dir = fw_dir / "src"
    config_path = src_dir / "generated_config.h"

    lines = [
        "// Auto-generated by soms_flash.py — DO NOT EDIT",
        "#pragma once",
        "",
        f'#define CFG_WIFI_SSID    "{defaults.get("wifi_ssid", "")}"',
        f'#define CFG_WIFI_PASS    "{defaults.get("wifi_password", "")}"',
        f'#define CFG_MQTT_SERVER  "{defaults.get("mqtt_server", "192.168.128.161")}"',
        f'#define CFG_MQTT_PORT    {defaults.get("mqtt_port", 1883)}',
        f'#define CFG_MQTT_USER    "{defaults.get("mqtt_user", "")}"',
        f'#define CFG_MQTT_PASS    "{defaults.get("mqtt_pass", "")}"',
        f'#define CFG_DEVICE_ID    "{device_cfg["device_id"]}"',
        f'#define CFG_ZONE         "{device_cfg.get("zone", "main")}"',
        "",
    ]

    config_path.write_text("\n".join(lines) + "\n")
    log.info("Generated %s", config_path)
    return config_path


def cleanup_config_h(fw_dir: Path) -> None:
    """Remove generated_config.h after build."""
    config_path = fw_dir / "src" / "generated_config.h"
    if config_path.exists():
        config_path.unlink()
        log.debug("Cleaned up %s", config_path)


# ---------------------------------------------------------------------------
# Build & Flash
# ---------------------------------------------------------------------------

def _get_pio() -> str:
    """Resolve path to pio command."""
    path = _find_tool("pio")
    if not path:
        raise FileNotFoundError("pio not found. Install with: uv pip install platformio")
    return path


def pio_build(fw_dir: Path) -> bool:
    """Run PlatformIO build (force recompile to pick up generated_config.h)."""
    pio = _get_pio()
    # Touch main source so PlatformIO detects the generated_config.h change
    main_src = fw_dir / "src" / "main.cpp"
    if main_src.exists():
        main_src.touch()
    log.info("Building %s ...", fw_dir.name)
    result = subprocess.run(
        [pio, "run", "-d", str(fw_dir)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.error("Build failed for %s:\n%s", fw_dir.name, result.stderr[-2000:])
        return False
    log.info("Build OK: %s", fw_dir.name)
    return True


def pio_upload(fw_dir: Path, port: str) -> bool:
    """Run PlatformIO upload to a specific port."""
    pio = _get_pio()
    log.info("Uploading to %s ...", port)
    result = subprocess.run(
        [pio, "run", "-d", str(fw_dir), "-t", "upload",
         "--upload-port", port],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        log.error("Upload failed on %s:\n%s", port, result.stderr[-2000:])
        return False
    log.info("Upload OK: %s", port)
    return True


# ---------------------------------------------------------------------------
# Serial verification
# ---------------------------------------------------------------------------

def verify_serial(port: str, dev_type: str, timeout: int = SERIAL_TIMEOUT) -> bool:
    """Monitor serial output for boot success markers."""
    marker = BOOT_MARKERS.get(dev_type, "=== Ready ===")
    intermediates = INTERMEDIATE_MARKERS.get(dev_type, [])
    seen = set()

    log.info("Verifying boot on %s (waiting for '%s', timeout=%ds)", port, marker, timeout)
    try:
        with serial.Serial(port, 115200, timeout=1) as ser:
            start = time.monotonic()
            while time.monotonic() - start < timeout:
                line = ser.readline().decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                log.debug("[serial] %s", line)

                # Check intermediate markers
                for im in intermediates:
                    if im in line and im not in seen:
                        seen.add(im)
                        log.info("  [+] %s", im)

                # Check final marker
                if marker in line:
                    log.info("Boot verified: %s", marker)
                    return True

    except serial.SerialException as e:
        log.error("Serial error on %s: %s", port, e)
        return False

    log.error("Boot verification timed out on %s", port)
    return False


# ---------------------------------------------------------------------------
# MQTT verification (optional)
# ---------------------------------------------------------------------------

def verify_mqtt(fleet: dict, device_cfg: dict, timeout: int = MQTT_VERIFY_TIMEOUT) -> bool:
    """Subscribe to heartbeat topic and wait for a message."""
    try:
        import paho.mqtt.client as mqtt_client
    except ImportError:
        log.warning("paho-mqtt not installed, skipping MQTT verification")
        return True

    defaults = fleet.get("defaults", {})
    broker = defaults.get("mqtt_server", "localhost")
    port = int(defaults.get("mqtt_port", 1883))
    user = defaults.get("mqtt_user", "")
    passwd = defaults.get("mqtt_pass", "")
    device_id = device_cfg["device_id"]
    zone = device_cfg.get("zone", "main")
    dev_type = device_cfg.get("type", "sensor")

    if dev_type == "camera":
        topic = f"office/{zone}/camera/{device_id}/status"
    else:
        topic = f"office/{zone}/sensor/{device_id}/heartbeat"

    received = threading.Event()

    def on_message(_client, _userdata, _msg):
        received.set()

    client = mqtt_client.Client(client_id=f"soms-flash-verify-{device_id}")
    if user:
        client.username_pw_set(user, passwd)
    client.on_message = on_message

    log.info("MQTT verify: connecting to %s:%d, topic=%s", broker, port, topic)
    try:
        client.connect(broker, port, keepalive=timeout + 10)
        client.subscribe(topic)
        client.loop_start()
        ok = received.wait(timeout=timeout)
        client.loop_stop()
        client.disconnect()
        if ok:
            log.info("MQTT heartbeat received from %s", device_id)
        else:
            log.error("MQTT heartbeat timeout for %s", device_id)
        return ok
    except Exception as e:
        log.error("MQTT verification error: %s", e)
        return False


# ---------------------------------------------------------------------------
# Flash pipeline
# ---------------------------------------------------------------------------

def flash_device(port: str, fleet: dict, mqtt_verify: bool = False) -> bool:
    """Full flash pipeline for one device on a given port."""
    log.info("=" * 60)
    log.info("Flash pipeline starting on %s", port)
    log.info("=" * 60)

    # 1. Detect device type from USB
    dev_type = detect_device_type_from_usb(port)
    if not dev_type:
        log.warning("Could not detect device type for %s, defaulting to 'sensor'", port)
        dev_type = "sensor"

    # 2. Read MAC
    mac = read_mac(port)
    if not mac:
        log.error("Failed to read MAC from %s", port)
        return False
    log.info("MAC: %s (type=%s)", mac, dev_type)

    # 3. Look up / auto-assign config
    device_cfg = get_device_config(fleet, mac, dev_type)
    dev_type = device_cfg.get("type", dev_type)  # config may override type
    device_id = device_cfg["device_id"]
    zone = device_cfg.get("zone", "main")
    log.info("Device: %s (zone=%s, type=%s)", device_id, zone, dev_type)

    # 4. Get firmware directory
    fw_dir = FW_DIRS.get(dev_type)
    if not fw_dir or not fw_dir.exists():
        log.error("No firmware directory for type '%s'", dev_type)
        return False

    build_lock = _build_locks.get(dev_type, threading.Lock())

    with build_lock:
        # 5. Generate config header
        config_path = generate_config_h(fleet, device_cfg, fw_dir)
        try:
            # 6. Build
            if not pio_build(fw_dir):
                return False
        finally:
            # Always clean up generated config
            cleanup_config_h(fw_dir)

    # 7. Upload
    if not pio_upload(fw_dir, port):
        return False

    # 8. Wait briefly for reboot
    time.sleep(2)

    # 9. Serial verification
    serial_ok = verify_serial(port, dev_type)
    if not serial_ok:
        log.error("Serial verification FAILED for %s on %s", device_id, port)
        return False

    # 10. Optional MQTT verification
    if mqtt_verify:
        mqtt_ok = verify_mqtt(fleet, device_cfg)
        if not mqtt_ok:
            log.warning("MQTT verification failed for %s (device may still be functional)", device_id)
            return False

    log.info("=" * 60)
    log.info("SUCCESS: %s (%s) flashed on %s", device_id, mac, port)
    log.info("=" * 60)
    return True


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_flash(args: argparse.Namespace) -> int:
    """Flash a single device."""
    fleet = load_fleet()
    ok = flash_device(args.port, fleet, mqtt_verify=args.mqtt_verify)
    return 0 if ok else 1


def cmd_identify(args: argparse.Namespace) -> int:
    """Identify a device (MAC + type) without flashing."""
    port = args.port
    dev_type = detect_device_type_from_usb(port)
    mac = read_mac(port)

    print(f"Port:   {port}")
    print(f"Type:   {dev_type or 'unknown'}")
    print(f"MAC:    {mac or 'read failed'}")

    if mac and FLEET_FILE.exists():
        fleet = load_fleet()
        devices = fleet.get("devices", {})
        if mac.upper() in devices:
            cfg = devices[mac.upper()]
            print(f"Fleet:  {cfg.get('device_id')} (zone={cfg.get('zone')}, type={cfg.get('type')})")
        else:
            print("Fleet:  (not registered)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all registered devices."""
    fleet = load_fleet()
    devices = fleet.get("devices", {})

    if not devices:
        print("No devices registered in fleet.yaml")
        return 0

    print(f"{'MAC':<20} {'Device ID':<22} {'Zone':<16} {'Type':<10}")
    print("-" * 68)
    for mac, cfg in devices.items():
        print(f"{mac:<20} {cfg.get('device_id', '?'):<22} "
              f"{cfg.get('zone', '?'):<16} {cfg.get('type', '?'):<10}")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """Watch for USB device connections and auto-flash."""
    try:
        import pyudev
    except ImportError:
        log.error("pyudev not installed. Install with: uv pip install pyudev")
        return 1

    fleet = load_fleet()
    executor = ThreadPoolExecutor(max_workers=4)
    active_ports: set[str] = set()

    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem="tty")

    log.info("Watching for USB device connections... (Ctrl+C to stop)")

    def _handle_add(device):
        dev_node = device.device_node
        if not dev_node or dev_node in active_ports:
            return

        # Check if it's likely an ESP32
        parent = device.find_parent("usb", "usb_device")
        if not parent:
            return

        vid = parent.attributes.get("idVendor", b"").decode()
        pid = parent.attributes.get("idProduct", b"").decode()
        if not vid or not pid:
            return

        try:
            key = (int(vid, 16), int(pid, 16))
        except ValueError:
            return

        if key not in USB_DEVICE_MAP:
            return

        chip, _ = USB_DEVICE_MAP[key]
        log.info("Detected %s on %s (%s)", chip, dev_node, f"{vid}:{pid}")

        active_ports.add(dev_node)
        # Allow device to settle
        time.sleep(1)

        def _flash_and_cleanup():
            try:
                # Reload fleet each time to pick up auto-assigned entries
                current_fleet = load_fleet()
                flash_device(dev_node, current_fleet, mqtt_verify=args.mqtt_verify)
            finally:
                active_ports.discard(dev_node)

        executor.submit(_flash_and_cleanup)

    def _handle_remove(device):
        dev_node = device.device_node
        if dev_node:
            active_ports.discard(dev_node)

    try:
        for device in iter(monitor.poll, None):
            if device.action == "add":
                _handle_add(device)
            elif device.action == "remove":
                _handle_remove(device)
    except KeyboardInterrupt:
        log.info("Watch stopped")
        executor.shutdown(wait=False)

    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SOMS ESP32 Auto-Flash Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    # watch
    p_watch = sub.add_parser("watch", help="Watch for USB connections and auto-flash")
    p_watch.add_argument("--mqtt-verify", action="store_true",
                         help="Verify MQTT heartbeat after flash")

    # flash
    p_flash = sub.add_parser("flash", help="Flash a single device")
    p_flash.add_argument("port", help="Serial port (e.g. /dev/ttyUSB0)")
    p_flash.add_argument("--mqtt-verify", action="store_true",
                         help="Verify MQTT heartbeat after flash")

    # list
    sub.add_parser("list", help="List registered devices from fleet.yaml")

    # identify
    p_id = sub.add_parser("identify", help="Read MAC and detect device type")
    p_id.add_argument("port", help="Serial port (e.g. /dev/ttyUSB0)")

    args = parser.parse_args()

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    commands = {
        "watch": cmd_watch,
        "flash": cmd_flash,
        "list": cmd_list,
        "identify": cmd_identify,
    }
    sys.exit(commands[args.command](args))


if __name__ == "__main__":
    main()
