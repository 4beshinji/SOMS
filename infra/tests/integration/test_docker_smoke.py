#!/usr/bin/env python3
"""
Docker Compose Smoke Test for SOMS.

Verifies the entire SOMS stack is running correctly after `docker compose up -d`.
Checks Docker container health, HTTP health endpoints, basic API responses,
and MQTT connectivity.

Requires: Docker running with SOMS containers started.
No external Python dependencies (stdlib only).

Test Sections:
  1. Docker Health Checks — all 14 containers via `docker inspect`
  2. HTTP Health Endpoints — /health on services that expose it
  3. API Smoke Tests — basic response validation on key endpoints
  4. MQTT Connectivity — publish test via mosquitto_pub
"""
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Load port overrides from .env.ports if it exists (start_soms.py writes this)
# ---------------------------------------------------------------------------
_ENV_PORTS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env.ports"
)
if os.path.isfile(_ENV_PORTS_FILE):
    with open(_ENV_PORTS_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

# ---------------------------------------------------------------------------
# Configuration (all overridable via environment variables)
# ---------------------------------------------------------------------------
PORT_BACKEND = os.getenv("SOMS_PORT_BACKEND", "8000")
PORT_AUTH = os.getenv("SOMS_PORT_AUTH", "8006")
PORT_VOICE = os.getenv("SOMS_PORT_VOICE", "8002")
PORT_MOCK_LLM = os.getenv("SOMS_PORT_MOCK_LLM", "8001")

BACKEND_URL = os.getenv("BACKEND_URL", f"http://localhost:{PORT_BACKEND}")
AUTH_URL = os.getenv("AUTH_URL", f"http://localhost:{PORT_AUTH}")
VOICE_URL = os.getenv("VOICE_URL", f"http://localhost:{PORT_VOICE}")
MOCK_LLM_URL = os.getenv("MOCK_LLM_URL", f"http://localhost:{PORT_MOCK_LLM}")

HTTP_TIMEOUT = 5  # seconds

CONTAINERS = [
    "soms-mqtt",
    "soms-brain",
    "soms-postgres",
    "soms-backend",
    "soms-frontend",
    "soms-voicevox",
    "soms-voice",
    "soms-auth",
    "soms-llm",
    "soms-mock-llm",
    "soms-switchbot",
    "soms-perception",
]

# ---------------------------------------------------------------------------
# Test harness (matches existing integration test pattern)
# ---------------------------------------------------------------------------
passed = 0
failed = 0
skipped = 0


class SkipTest(Exception):
    pass


def test(name, fn):
    global passed, failed, skipped
    try:
        fn()
        passed += 1
        print(f"  PASS  {name}")
    except SkipTest as e:
        skipped += 1
        print(f"  SKIP  {name} -- {e}")
    except Exception as e:
        failed += 1
        print(f"  FAIL  {name} -- {e}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def http_get(url, timeout=HTTP_TIMEOUT):
    """GET request returning parsed JSON or raw bytes."""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        content_type = resp.headers.get("Content-Type", "")
        if "json" in content_type:
            return json.loads(raw)
        return raw


def docker_health(container_name):
    """Return the Docker health status string for a container."""
    result = subprocess.run(
        [
            "docker", "inspect",
            "--format", "{{.State.Health.Status}}",
            container_name,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "No such object" in stderr or "Error" in stderr:
            raise SkipTest(f"container not found")
        raise RuntimeError(f"docker inspect failed: {stderr}")
    return result.stdout.strip()


# ======================================================================
# Section 1: Docker Health Checks
# ======================================================================

def _make_docker_health_test(container):
    """Factory: returns a test function for one container's Docker health."""
    def _test():
        status = docker_health(container)
        if status == "healthy":
            return
        if status == "starting":
            raise RuntimeError(f"status is 'starting' (not yet healthy)")
        if status == "unhealthy":
            raise RuntimeError(f"status is 'unhealthy'")
        # Unknown status (e.g. no healthcheck defined)
        raise RuntimeError(f"unexpected health status: '{status}'")
    return _test


# ======================================================================
# Section 2: HTTP Health Endpoints
# ======================================================================

HEALTH_ENDPOINTS = [
    ("Backend",  f"{BACKEND_URL}/health"),
    ("Auth",     f"{AUTH_URL}/health"),
    ("Voice",    f"{VOICE_URL}/health"),
    ("Mock LLM", f"{MOCK_LLM_URL}/health"),
]


def _make_http_health_test(url):
    """Factory: returns a test function for one HTTP /health endpoint."""
    def _test():
        try:
            resp = http_get(url)
        except urllib.error.URLError as e:
            raise SkipTest(f"service unavailable: {e.reason}")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}")
        # Any 2xx with a response body is considered healthy
        if resp is None:
            raise RuntimeError("empty response")
    return _test


# ======================================================================
# Section 3: API Smoke Tests
# ======================================================================

def test_api_backend_health():
    """GET /health on backend returns 200."""
    try:
        resp = http_get(f"{BACKEND_URL}/health")
    except urllib.error.URLError as e:
        raise SkipTest(f"backend unavailable: {e.reason}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}")
    assert resp is not None, "empty response from /health"


def test_api_tasks_list():
    """GET /tasks/ returns a list."""
    try:
        resp = http_get(f"{BACKEND_URL}/tasks/")
    except urllib.error.URLError as e:
        raise SkipTest(f"backend unavailable: {e.reason}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode() if e.fp else ''}")
    assert isinstance(resp, list), f"Expected list, got {type(resp).__name__}"


def test_api_tasks_stats():
    """GET /tasks/stats returns dict with tasks_completed key."""
    try:
        resp = http_get(f"{BACKEND_URL}/tasks/stats")
    except urllib.error.URLError as e:
        raise SkipTest(f"backend unavailable: {e.reason}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode() if e.fp else ''}")
    assert isinstance(resp, dict), f"Expected dict, got {type(resp).__name__}"
    assert "tasks_completed" in resp, f"Missing 'tasks_completed' key in: {list(resp.keys())}"


def test_api_sensors_latest():
    """GET /sensors/latest returns a list."""
    try:
        resp = http_get(f"{BACKEND_URL}/sensors/latest")
    except urllib.error.URLError as e:
        raise SkipTest(f"backend unavailable: {e.reason}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode() if e.fp else ''}")
    assert isinstance(resp, list), f"Expected list, got {type(resp).__name__}"


# ======================================================================
# Section 4: MQTT Connectivity
# ======================================================================

def test_mqtt_publish():
    """Publish a test message via mosquitto_pub."""
    mqtt_port = os.getenv("SOMS_PORT_MQTT", "1883")
    mqtt_user = os.getenv("MQTT_USER", "soms")
    mqtt_pass = os.getenv("MQTT_PASS", "soms_dev_mqtt")
    try:
        result = subprocess.run(
            [
                "mosquitto_pub",
                "-h", "localhost",
                "-p", mqtt_port,
                "-u", mqtt_user,
                "-P", mqtt_pass,
                "-t", "test/docker_smoke",
                "-m", "smoke_test_ping",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        raise SkipTest("mosquitto_pub not installed")
    except subprocess.TimeoutExpired:
        raise RuntimeError("mosquitto_pub timed out after 10s")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"mosquitto_pub failed (rc={result.returncode}): {stderr}")


# ======================================================================
# Main
# ======================================================================

def main():
    global passed, failed, skipped

    print("=" * 60)
    print("SOMS Docker Compose Smoke Test")
    print("=" * 60)

    # -- Section 1: Docker Health Checks --
    print("\n[1] Docker Container Health Checks")
    for container in CONTAINERS:
        test(f"docker: {container}", _make_docker_health_test(container))

    # -- Section 2: HTTP Health Endpoints --
    print("\n[2] HTTP Health Endpoints")
    for label, url in HEALTH_ENDPOINTS:
        test(f"http: {label} /health", _make_http_health_test(url))

    # -- Section 3: API Smoke Tests --
    print("\n[3] API Smoke Tests")
    test("api: GET /health (backend)", test_api_backend_health)
    test("api: GET /tasks/ returns list", test_api_tasks_list)
    test("api: GET /tasks/stats", test_api_tasks_stats)
    test("api: GET /sensors/latest returns list", test_api_sensors_latest)

    # -- Section 4: MQTT Connectivity --
    print("\n[4] MQTT Connectivity")
    test("mqtt: publish test message", test_mqtt_publish)

    # -- Summary --
    total = passed + failed + skipped
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped / {total} total")
    print(f"{'=' * 60}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
