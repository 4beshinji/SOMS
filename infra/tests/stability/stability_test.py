#!/usr/bin/env python3
"""SOMS 24-hour stability test.

Monitors all SOMS services over a configurable duration, collecting health
status, resource usage, and error counts.  Produces a JSON log and a
summary report on completion.

Usage:
    python3 infra/tests/stability/stability_test.py --duration 24h
    python3 infra/tests/stability/stability_test.py --duration 1h --compose-file infra/docker-compose.yml
"""

import argparse
import asyncio
import datetime
import json
import re
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Service definitions
# ---------------------------------------------------------------------------

# Services with HTTP health endpoints reachable from the host.
# (container_name, host_url)
HTTP_SERVICES = [
    ("soms-backend",  "http://localhost:8000/health"),
    ("soms-voice",    "http://localhost:8002/health"),
    ("soms-wallet",   "http://localhost:8003/health"),
    ("soms-auth",     "http://localhost:8006/health"),
    ("soms-mock-llm", "http://localhost:8001/health"),
    ("soms-frontend", "http://localhost:80/"),
]

# Services whose health is checked via docker inspect (healthcheck status).
DOCKER_HEALTH_SERVICES = [
    "soms-mqtt",
    "soms-postgres",
    "soms-brain",
    "soms-voicevox",
    "soms-wallet-app",
    "soms-switchbot",
    "soms-perception",
    "soms-llm",
]

# All container names we track for resource stats and log scanning.
ALL_CONTAINERS = [s[0] for s in HTTP_SERVICES] + DOCKER_HEALTH_SERVICES

# Patterns that indicate errors in docker logs.
ERROR_PATTERNS = re.compile(
    r"(ERROR|CRITICAL|Traceback \(most recent call last\)|Exception|FATAL)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_duration(s: str) -> int:
    """Parse a human-readable duration string into seconds.

    Accepts formats like '30s', '5m', '1h', '24h', '1d'.
    """
    s = s.strip().lower()
    match = re.fullmatch(r"(\d+)\s*([smhd]?)", s)
    if not match:
        raise ValueError(f"Invalid duration: {s!r}")
    value = int(match.group(1))
    unit = match.group(2) or "s"
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multiplier[unit]


def _http_check(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Perform a simple HTTP GET and return (ok, detail)."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(4096).decode("utf-8", errors="replace")
            return True, body[:200]
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)[:200]


def _docker_health(container: str) -> tuple[bool, str]:
    """Return (healthy, status_string) by inspecting docker healthcheck."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", container],
            capture_output=True,
            text=True,
            timeout=10,
        )
        status = result.stdout.strip()
        if not status:
            return False, "not-found"
        return status == "healthy", status
    except Exception as exc:
        return False, str(exc)[:200]


def _docker_stats() -> dict[str, dict]:
    """Collect CPU% and memory usage for all running containers."""
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format",
             "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        stats = {}
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            name = parts[0]
            cpu_str = parts[1].replace("%", "").strip()
            mem_usage = parts[2].strip()
            mem_pct_str = parts[3].replace("%", "").strip()
            try:
                cpu = float(cpu_str)
            except ValueError:
                cpu = 0.0
            try:
                mem_pct = float(mem_pct_str)
            except ValueError:
                mem_pct = 0.0
            # Parse memory usage (e.g., "123.4MiB / 16GiB")
            mem_bytes = _parse_mem(mem_usage.split("/")[0].strip()) if "/" in mem_usage else 0
            stats[name] = {
                "cpu_percent": cpu,
                "mem_bytes": mem_bytes,
                "mem_percent": mem_pct,
                "mem_display": mem_usage,
            }
        return stats
    except Exception:
        return {}


def _parse_mem(s: str) -> int:
    """Parse memory string like '123.4MiB' into bytes."""
    s = s.strip()
    units = {"B": 1, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3, "TIB": 1024**4,
             "KB": 1000, "MB": 1000**2, "GB": 1000**3}
    match = re.match(r"([\d.]+)\s*(\w+)", s, re.IGNORECASE)
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2).upper()
    return int(value * units.get(unit, 1))


def _format_mem(b: int) -> str:
    """Format bytes into human-readable string."""
    if b >= 1024**3:
        return f"{b / 1024**3:.1f} GiB"
    if b >= 1024**2:
        return f"{b / 1024**2:.1f} MiB"
    if b >= 1024:
        return f"{b / 1024:.1f} KiB"
    return f"{b} B"


def _scan_logs(container: str, since_seconds: int = 90) -> int:
    """Count error-pattern matches in recent docker logs."""
    try:
        since = f"{since_seconds}s"
        result = subprocess.run(
            ["docker", "logs", "--since", since, container],
            capture_output=True,
            text=True,
            timeout=15,
        )
        text = result.stdout + result.stderr
        return len(ERROR_PATTERNS.findall(text))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


class StabilityTest:
    def __init__(self, duration_seconds: int, compose_file: str, interval: int = 60):
        self.duration = duration_seconds
        self.compose_file = compose_file
        self.interval = interval
        self.stop_event = asyncio.Event()

        # Per-service accumulators
        self.checks_total: dict[str, int] = {}
        self.checks_healthy: dict[str, int] = {}
        self.error_counts: dict[str, int] = {}
        self.peak_mem: dict[str, int] = {}
        self.peak_cpu: dict[str, float] = {}

        # Raw log entries
        self.log_entries: list[dict] = []

        # Timing
        self.start_time = 0.0
        self.end_time = 0.0

    def _signal_handler(self):
        print("\n[SIGINT] Graceful shutdown requested...")
        self.stop_event.set()

    async def run(self):
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        self.start_time = time.time()
        deadline = self.start_time + self.duration

        duration_str = _format_duration(self.duration)
        print(f"=== SOMS Stability Test ===")
        print(f"Duration : {duration_str}")
        print(f"Interval : {self.interval}s")
        print(f"Compose  : {self.compose_file}")
        print(f"Started  : {datetime.datetime.now().isoformat(timespec='seconds')}")
        print(f"{'=' * 50}")
        print()

        tick = 0
        while not self.stop_event.is_set():
            tick += 1
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            entry = self._collect_tick(tick)
            self.log_entries.append(entry)
            self._print_tick(tick, entry, remaining)

            # Wait for next interval or stop
            try:
                await asyncio.wait_for(
                    self.stop_event.wait(),
                    timeout=min(self.interval, remaining),
                )
            except asyncio.TimeoutError:
                pass

        self.end_time = time.time()
        self._write_log()
        self._print_summary()

        return 0 if self._is_pass() else 1

    def _collect_tick(self, tick: int) -> dict:
        """Run one collection cycle."""
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        entry: dict = {"tick": tick, "timestamp": ts, "services": {}}

        # HTTP health checks
        for container, url in HTTP_SERVICES:
            ok, detail = _http_check(url)
            self._record(container, ok)
            entry["services"][container] = {"healthy": ok, "detail": detail}

        # Docker healthcheck services
        for container in DOCKER_HEALTH_SERVICES:
            ok, detail = _docker_health(container)
            self._record(container, ok)
            entry["services"][container] = {"healthy": ok, "detail": detail}

        # Resource stats
        stats = _docker_stats()
        entry["stats"] = {}
        for container in ALL_CONTAINERS:
            if container in stats:
                s = stats[container]
                entry["stats"][container] = s
                # Track peaks
                if s["mem_bytes"] > self.peak_mem.get(container, 0):
                    self.peak_mem[container] = s["mem_bytes"]
                if s["cpu_percent"] > self.peak_cpu.get(container, 0.0):
                    self.peak_cpu[container] = s["cpu_percent"]

        # Log scanning
        entry["errors"] = {}
        for container in ALL_CONTAINERS:
            err_count = _scan_logs(container, since_seconds=self.interval + 30)
            if err_count > 0:
                entry["errors"][container] = err_count
                self.error_counts[container] = self.error_counts.get(container, 0) + err_count

        return entry

    def _record(self, container: str, healthy: bool):
        self.checks_total[container] = self.checks_total.get(container, 0) + 1
        if healthy:
            self.checks_healthy[container] = self.checks_healthy.get(container, 0) + 1

    def _print_tick(self, tick: int, entry: dict, remaining: float):
        ts = entry["timestamp"]
        remain_str = _format_duration(int(remaining))

        # Build compact status line
        statuses = []
        for container, info in entry["services"].items():
            short_name = container.replace("soms-", "")
            mark = "OK" if info["healthy"] else "FAIL"
            statuses.append(f"{short_name}={mark}")
        status_line = " | ".join(statuses)

        # Error counts this tick
        tick_errors = sum(entry.get("errors", {}).values())
        err_str = f" | errors={tick_errors}" if tick_errors > 0 else ""

        print(f"[{ts}] tick={tick} remaining={remain_str} | {status_line}{err_str}")

    def _is_pass(self) -> bool:
        """Determine overall pass/fail."""
        for container in ALL_CONTAINERS:
            total = self.checks_total.get(container, 0)
            healthy = self.checks_healthy.get(container, 0)
            if total == 0:
                continue
            uptime_pct = healthy / total * 100
            # Fail if any service was below 95% uptime
            if uptime_pct < 95.0:
                return False
        return True

    def _write_log(self):
        """Write raw log entries to a JSON file."""
        log_dir = Path(__file__).parent
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"stability_log_{ts}.json"

        data = {
            "start": datetime.datetime.fromtimestamp(self.start_time).isoformat(timespec="seconds"),
            "end": datetime.datetime.fromtimestamp(self.end_time).isoformat(timespec="seconds"),
            "duration_seconds": int(self.end_time - self.start_time),
            "interval_seconds": self.interval,
            "ticks": self.log_entries,
        }
        with open(log_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\nLog written to: {log_file}")

    def _print_summary(self):
        elapsed = int(self.end_time - self.start_time)
        elapsed_str = _format_duration(elapsed)
        verdict = "PASS" if self._is_pass() else "FAIL"

        print()
        print(f"{'=' * 70}")
        print(f"  SOMS Stability Test Summary")
        print(f"{'=' * 70}")
        print(f"  Duration : {elapsed_str}")
        print(f"  Verdict  : {verdict}")
        print(f"{'=' * 70}")
        print()
        print(f"  {'Service':<22} {'Uptime':>8} {'Checks':>8} {'Errors':>8} {'Peak Mem':>12} {'Peak CPU':>10}")
        print(f"  {'-' * 22} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 12} {'-' * 10}")

        for container in ALL_CONTAINERS:
            total = self.checks_total.get(container, 0)
            healthy = self.checks_healthy.get(container, 0)
            errors = self.error_counts.get(container, 0)
            peak_m = self.peak_mem.get(container, 0)
            peak_c = self.peak_cpu.get(container, 0.0)

            if total > 0:
                uptime = f"{healthy / total * 100:.1f}%"
                checks = f"{healthy}/{total}"
            else:
                uptime = "N/A"
                checks = "0/0"

            mem_str = _format_mem(peak_m) if peak_m > 0 else "-"
            cpu_str = f"{peak_c:.1f}%" if peak_c > 0 else "-"
            short = container.replace("soms-", "")

            print(f"  {short:<22} {uptime:>8} {checks:>8} {errors:>8} {mem_str:>12} {cpu_str:>10}")

        print()
        print(f"{'=' * 70}")
        print()


def _format_duration(seconds: int) -> str:
    """Format seconds as 'Xh Ym Zs'."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    if s > 0 or not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="SOMS stability test")
    parser.add_argument(
        "--duration",
        default="1h",
        help="Test duration (e.g. 30s, 5m, 1h, 24h, 1d). Default: 1h",
    )
    parser.add_argument(
        "--compose-file",
        default="infra/docker-compose.yml",
        help="Path to docker-compose file. Default: infra/docker-compose.yml",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Check interval in seconds. Default: 60",
    )
    args = parser.parse_args()

    try:
        duration = parse_duration(args.duration)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    test = StabilityTest(
        duration_seconds=duration,
        compose_file=args.compose_file,
        interval=args.interval,
    )

    exit_code = asyncio.run(test.run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
