# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SOMS (Symbiotic Office Management System)** — an autonomous, event-driven office management system combining an LLM "brain" with IoT edge devices, computer vision, and a credit-based economy for human-AI collaboration. The LLM makes real-time decisions about the office environment (lighting, HVAC, task delegation) using sensor data and camera feeds.

## Python Environment

Use **uv** for all Python package management. A project-level virtual environment lives at `.venv/`.

```bash
# Create venv (first time)
uv venv .venv

# Install a package
uv pip install <package> --python .venv/bin/python

# Run a script inside the venv
.venv/bin/python infra/tests/integration/test_sensor_api.py

# Or activate and use normally
source .venv/bin/activate
python infra/tests/...
```

**Never use `pip install` directly** (system pip is restricted). Always use `uv pip install`.

## Build & Run Commands

All services run via Docker Compose from the `infra/` directory.

```bash
# Initial setup (create volumes, build containers)
cp env.example .env
./infra/scripts/setup_dev.sh

# Full simulation (no GPU/hardware required) — uses mock LLM + virtual edge devices
./infra/scripts/start_virtual_edge.sh

# Production (requires AMD ROCm GPU + real hardware)
docker compose -f infra/docker-compose.yml up -d --build

# Rebuild a single service
docker compose -f infra/docker-compose.yml up -d --build <service-name>

# View logs
docker logs -f soms-brain
docker logs -f soms-perception
```

Service names in docker-compose: `mosquitto`, `brain`, `postgres`, `backend`, `frontend`, `voicevox`, `voice-service`, `wallet`, `wallet-app`, `auth`, `ollama`, `mock-llm`, `perception`, `switchbot`

### Frontend Development

```bash
cd services/dashboard/frontend
pnpm install
pnpm run dev      # Vite dev server
pnpm run build    # tsc -b && vite build
pnpm run lint     # ESLint
```

### Testing

Unit tests (pytest, no running services required — **724 tests total**):
```bash
# All unit tests (run per-service to avoid conftest collisions)
for d in services/brain/tests services/auth/tests services/voice/tests services/dashboard/backend/tests services/wallet/tests services/switchbot/tests services/perception/tests; do echo "=== $d ===" && .venv/bin/python -m pytest "$d" -v --tb=short; done

# Per service
.venv/bin/python -m pytest services/brain/tests/              # Brain: 167 tests (queue, sanitizer, sensor fusion, tools, executor, dashboard client)
.venv/bin/python -m pytest services/auth/tests/               # Auth: 97 tests (OAuth, JWT, middleware)
.venv/bin/python -m pytest services/voice/tests/              # Voice: 79 tests (API endpoints, rejection/acceptance/currency stock)
.venv/bin/python -m pytest services/dashboard/backend/tests/  # Dashboard: 172 tests (JWT auth, protected endpoints, task/sensor/device/voice CRUD)
.venv/bin/python -m pytest services/wallet/tests/             # Wallet: 64 tests (JWT auth, financial endpoints)
.venv/bin/python -m pytest services/switchbot/tests/          # SwitchBot: 59 tests (config, device manager, API)
.venv/bin/python -m pytest services/perception/tests/         # Perception: 86 tests (ArUco, ReID, tracklet, fall detection)
```

Integration tests (standalone scripts, requires running services):
```bash
python3 infra/tests/integration/integration_test_mock.py           # Main integration (7 scenarios)
python3 infra/tests/integration/test_task_scheduling.py
python3 infra/tests/integration/test_world_model.py
python3 infra/tests/integration/test_human_task.py
python3 infra/tests/integration/test_wallet_integration.py         # F.1: Wallet service direct
python3 infra/tests/e2e/test_wallet_dashboard_e2e.py               # F.3: Wallet <-> Dashboard cross-service
python3 infra/tests/integration/test_sensor_api.py                 # C.2: Sensor Data API endpoints
```

Perception diagnostic tests (requires GPU/camera):
```bash
python3 services/perception/test_activity.py
python3 services/perception/test_discovery.py
python3 services/perception/test_yolo_detect.py
```

## Architecture

### 4-Layer Design

1. **Central Intelligence** (`services/brain/`) — LLM-driven decision engine using a ReAct (Think→Act→Observe) cognitive loop. Cycles every 30s or on new MQTT events, max 5 iterations per cycle, 3s event batch delay.
2. **Perception** (`services/perception/`) — YOLOv11 vision system with pluggable monitors (occupancy, whiteboard, activity, fall detection) defined in `config/monitors.yaml`. Uses host networking for camera access.
3. **Communication** — MQTT broker (Mosquitto) as central message bus. Uses MCP (Model Context Protocol) over MQTT with JSON-RPC 2.0 payloads.
4. **Edge** (`edge/`) — ESP32 devices for sensors and relays. Two firmware variants: MicroPython (`edge/office/`) for production, PlatformIO C++ (`edge/test-edge/`) for development. Shared MicroPython library in `edge/lib/soms_mcp.py`. Diagnostic scripts in `edge/tools/`. All devices use MCP (JSON-RPC 2.0) and publish per-channel telemetry (`{"value": X}`) for WorldModel compatibility.
5. **SensorSwarm** (`edge/swarm/`, `edge/lib/swarm/`) — Hub+Leaf 2-tier sensor network. Hub (ESP32 with WiFi+MQTT) aggregates Leaf nodes via ESP-NOW, UART, I2C, or BLE. Binary protocol (5-245 bytes, MAGIC 0x53, XOR checksum). Device IDs use dot notation: `swarm_hub_01.leaf_env_01`. See `edge/swarm/README.md`.
6. **Wallet** (`services/wallet/`) — Double-entry credit ledger. System wallet (user_id=0) issues credits. Task bounty (500-5000), device XP with dynamic multiplier (1.0x-3.0x).

### Federation (Phase 1)

- `config/federation.yaml` — Region identity configuration
- `SOMS_REGION_ID` env var overrides the YAML config
- All models include `region_id` column (default: "local")
- reference_id format: `{region_id}:{type}:{id}` (e.g., "local:task:42")

### Service Ports

| Service | Port | Container Name |
|---------|------|----------------|
| Dashboard Frontend (nginx) | 80 | soms-frontend |
| Dashboard Backend API | 8000 | soms-backend |
| Mock LLM | 8001 | soms-mock-llm |
| Voice Service | 8002 | soms-voice |
| Wallet Service | 127.0.0.1:8003 (localhost only) | soms-wallet |
| Wallet App (PWA) | 8004 | soms-wallet-app |
| PostgreSQL | 127.0.0.1:5432 (localhost only) | soms-postgres |
| VOICEVOX Engine | 50021 | soms-voicevox |
| Ollama (LLM) | 11434 | soms-ollama |
| Auth Service | 127.0.0.1:8006 (localhost only) | soms-auth |
| SwitchBot Bridge (Webhook) | 8005 | soms-switchbot |
| MQTT | 1883 (TCP) / 9001 (WebSocket) | soms-mqtt |

### MQTT Topic Structure

```
# Sensor telemetry (per-channel, payload: {"value": X})
office/{zone}/{device_type}/{device_id}/{channel}
  e.g. office/main/sensor/env_01/temperature

# SensorSwarm (Hub-forwarded, dot-separated device_id)
office/{zone}/sensor/{hub_id}.{leaf_id}/{channel}
  e.g. office/main/sensor/swarm_hub_01.leaf_env_01/temperature

# Camera status
office/{zone}/camera/{camera_id}/status

# Activity detection
office/{zone}/activity/{monitor_id}

# MCP device control (JSON-RPC 2.0)
mcp/{agent_id}/request/{method}
mcp/{agent_id}/response/{request_id}

# Safety alerts (fall detection etc.)
office/{zone}/safety/fall

# Task completion report (published by backend)
office/{zone}/task_report/{task_id}

# Heartbeat (60s interval)
{topic_prefix}/heartbeat
```

Brain subscribes to `office/#` and `mcp/+/response/#`.

### Inter-Service Communication

- **Brain ↔ Edge Devices**: MCP over MQTT (JSON-RPC 2.0)
- **Brain → Dashboard**: REST API (`POST/GET/PUT /tasks`)
- **Brain → Voice**: REST API (`POST /api/voice/announce`, `POST /api/voice/synthesize`)
- **Perception → MQTT**: Publishes detection results to broker
- **Backend → MQTT**: Publishes task completion reports to `office/{zone}/task_report/{task_id}` (authenticated)
- **Brain ← MQTT**: Subscribes to sensor telemetry and perception events, triggers cognitive cycles on state changes
- **MQTT Authentication**: All MQTT clients use username/password auth (`MQTT_USER`/`MQTT_PASS`, default: `soms`/`soms_dev_mqtt`)

### Brain Service Internals (`services/brain/src/`)

- `main.py` — `Brain` class: ReAct cognitive loop, MQTT event handler, component orchestration
- `llm_client.py` — Async OpenAI-compatible API wrapper (aiohttp, 120s timeout)
- `mcp_bridge.py` — MQTT ↔ JSON-RPC 2.0 translation layer (10s timeout per call)
- `world_model/` — `WorldModel` maintains unified zone state from MQTT; `SensorFusion` aggregates readings; `ZoneState`/`EnvironmentData`/`Event` dataclasses. Routes `office/{zone}/safety/fall` to critical events
- `task_scheduling/` — `TaskQueueManager` with priority scoring and decision logic
- `tool_registry.py` — OpenAI function-calling schema definitions (6 tools)
- `tool_executor.py` — Routes and executes tool calls with sanitizer validation
- `system_prompt.py` — Constitutional AI system prompt builder (includes fall detection response guidance)
- `sanitizer.py` — Input validation and security
- `dashboard_client.py` — REST client for dashboard backend
- `task_reminder.py` — Periodic reminder service (re-announces tasks after 1 hour)
- `device_registry.py` — Device state tracking with adaptive timeout calculation
- `wallet_bridge.py` — Forwards heartbeats and device metrics to Wallet service
- `spatial_config.py` — Office layout geometry and zone/device positions loader
- `federation_config.py` — Region identity configuration loader
- `event_store/` — `EventWriter` for recording LLM decisions + `HourlyAggregator` (PostgreSQL)

### LLM Tools (defined in `tool_registry.py`)

| Tool | Purpose | Key Params |
|------|---------|------------|
| `create_task` | Create human task on dashboard with bounty | title, description, bounty (500-5000), urgency (0-4), zone |
| `send_device_command` | Control edge device via MCP | agent_id, tool_name, arguments (JSON) |
| `get_zone_status` | Query WorldModel for zone details | zone_id |
| `speak` | Voice-only announcement (ephemeral, no dashboard) | message (70 chars max), zone, tone |
| `get_active_tasks` | List current tasks (duplicate prevention) | — |
| `get_device_status` | Check device network/battery status | zone_id (optional, defaults to all zones) |

### Perception Service (`services/perception/src/`)

- Monitors are pluggable: `OccupancyMonitor`, `WhiteboardMonitor`, `ActivityMonitor`, `TrackingMonitor` (all extend `MonitorBase`)
- Image sources abstracted: `RTSPSource`, `MQTTSource`, `HTTPStream` via `ImageSourceFactory`
- `activity_analyzer.py` — Tiered pose buffer (4 tiers, up to 4 hours) with posture normalization
- `fall_detector.py` — Geometric heuristic fall detection with furniture-aware discrimination. Uses torso angle, head position, bbox ratio, rapid transition, and ankle spread as positive signals; furniture IoU and hip-in-furniture as negative penalties. State machine: NORMAL → SUSPICIOUS (5s) → FALL_CONFIRMED → ALERT_SENT, with 120s cooldown. Integrated into `ActivityMonitor.process_results()`, publishes to `office/{zone}/safety/fall`
- `camera_discovery.py` — Async TCP port scan + URL probe + YOLO verification for auto-discovery
- `tracking/` — MTMC (Multi-Target Multi-Camera) person tracking: `CrossCameraTracker`, `ArUcoCalibrator` (coordinate calibration), `ReIDEmbedder` (person re-identification), `Tracklet`, `MTMCPublisher`, `Homography` (camera-to-floor transform)
- Monitor config in `services/perception/config/monitors.yaml` includes YOLO model paths, camera-zone mappings, tracker/ReID settings, fall detection parameters, and discovery settings

### SwitchBot Cloud Bridge (`services/switchbot/src/`)

Bridges SwitchBot Cloud API v1.1 devices into SOMS via MQTT. Uses the same telemetry format (`{"value": X}` per-channel) and MCP JSON-RPC 2.0 protocol as ESP32 edge devices — Brain, WorldModel, and DeviceRegistry require no changes.

- `main.py` — Async entry point, orchestrates all components
- `config_loader.py` — YAML config with `${ENV_VAR}` expansion
- `switchbot_api.py` — HMAC-SHA256 authenticated Cloud API client with rate limiting (10,000/day)
- `mqtt_bridge.py` — MQTT connection, MCP request routing to devices
- `device_manager.py` — Polling scheduler (sensors: 2min, actuators: 5min), heartbeat publisher (60s)
- `webhook_server.py` — Optional aiohttp webhook receiver for real-time event push
- `devices/` — Device type implementations (meter, bot, curtain, plug, lock, light, motion_sensor, contact_sensor, ir_device)

Config: `config/switchbot.yaml`. Env vars: `SWITCHBOT_TOKEN`, `SWITCHBOT_SECRET`.

### Auth Service (`services/auth/src/`)

OAuth-based authentication service (Slack + GitHub) with JWT token issuance. Shares the same PostgreSQL database as other services. Creates users in `public.users` on first OAuth login and stores OAuth account links in `auth` schema.

- `main.py` — FastAPI app, lifespan creates `auth` schema and tables
- `config.py` — Settings from environment variables
- `database.py` — SQLAlchemy async engine (same pattern as wallet)
- `models.py` — `OAuthAccount`, `RefreshToken` (auth schema)
- `schemas.py` — Pydantic request/response models
- `security.py` — JWT (HS256) generation/verification, OAuth state tokens
- `user_service.py` — User lookup/auto-creation in `public.users`
- `providers/` — OAuth provider implementations (base ABC, Slack OpenID Connect, GitHub OAuth)
- `routers/oauth.py` — `GET /{provider}/login`, `GET /{provider}/callback`
- `routers/token.py` — `POST /token/refresh`, `POST /token/revoke`, `GET /token/me`

**JWT Spec**: HS256, 15min access token (`{ sub: user_id, username, display_name, iss: "soms-auth" }`), 30-day refresh token (SHA-256 hashed, single-use rotation). Shared `JWT_SECRET` env var across auth/wallet/dashboard.

**nginx routing** (wallet-app): `/api/auth/*` → auth:8000

### nginx Routing (`services/dashboard/frontend/nginx.conf`)

All upstreams use Docker DNS lazy resolution (`resolver 127.0.0.11` + `set $var`) so nginx starts even when upstream services are unavailable (returns 502 on request instead of crashing).

| Path | Upstream |
|------|----------|
| `/` | SPA (index.html) |
| `/api/wallet/` | wallet:8000 |
| `/api/voice/` | voice-service:8000 |
| `/api/` | backend:8000 |
| `/audio/` | voice-service:8000 |

### Dashboard Backend API (`services/dashboard/backend/`)

SQLAlchemy async ORM with PostgreSQL (asyncpg). Key models: `Task` (27 columns: bounty/urgency/voice/queue/assignment/federation fields), `VoiceEvent` (tone: neutral/caring/humorous/alert), `User` (username, display_name, is_active), `SystemStats` (total_xp, tasks_completed, tasks_created).

Task duplicate detection: Stage 1 (title + location exact match), Stage 2 (zone + task_type).

Routers: `routers/tasks.py` (CRUD + wallet integration), `routers/users.py` (list/get/create/update), `routers/voice_events.py`, `routers/sensors.py` (read-only sensor data), `routers/spatial.py` (building layout + live positions), `routers/devices.py` (device position management). Swagger UI at `:8000/docs`.

#### Task Router (`routers/tasks.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tasks/` | List non-expired tasks (paginated) |
| POST | `/tasks/` | Create task (duplicate detection Stage 1 & 2) |
| PUT | `/tasks/{task_id}/accept` | Assign task to user |
| PUT | `/tasks/{task_id}/complete` | Mark completed and pay bounty via wallet |
| PUT | `/tasks/{task_id}/reminded` | Update last_reminded_at timestamp |
| GET | `/tasks/queue` | List queued (not yet dispatched) tasks |
| PUT | `/tasks/{task_id}/dispatch` | Mark queued task as dispatched |
| GET | `/tasks/stats` | Task statistics (counts, XP, completions) |

Sensor data access uses Repository pattern (`repositories/`): `SensorDataRepository` ABC with `PgSensorRepository` (PostgreSQL) implementation. `SpatialDataRepository` ABC with `PgSpatialRepository`. DI via `repositories/deps.py`. See `docs/architecture/adr-sensor-api-repository-pattern.md`.

#### Sensor Data API (`routers/sensors.py`)

| Method | Path | Description | Parameters |
|--------|------|-------------|------------|
| GET | `/sensors/latest` | Latest value per zone × channel | `?zone=` |
| GET | `/sensors/time-series` | Chart-ready time series | `?zone=&channel=&window=1h&start=&end=&limit=168` |
| GET | `/sensors/zones` | All-zone overview snapshot | — |
| GET | `/sensors/events` | WorldModel event feed | `?zone=&limit=50` |
| GET | `/sensors/llm-activity` | LLM decision-making summary | `?hours=24` |

#### Spatial 3-Layer Model

空間情報はライフサイクルごとに3層に分離される:

| Layer | 内容 | ストレージ | 更新方法 |
|-------|------|----------|---------|
| 1 Topology | ゾーンポリゴン・建物寸法・ArUco 座標 | `config/spatial.yaml` (git) | テキストエディタ + 再起動 |
| 2 Placement | デバイス・カメラ位置 (x, y, z, FOV) | `device_positions` / `camera_positions` テーブル | Dashboard UI ドラッグ編集 |
| 3 Observations | ライブ検出・ヒートマップ集計 | `events.spatial_*` テーブル | Perception が自動書き込み |

ADR: `docs/architecture/adr-spatial-world-model.md`

#### Unified Spaces API (`routers/spaces.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/spaces` | Zone 一覧 (Layer 1) |
| GET | `/spaces/{zone}` | Zone 詳細 (Layer 1+2 マージ) |
| PUT | `/spaces/{zone}/devices/{device_id}` | デバイス位置更新 (Layer 2) |
| PUT | `/spaces/{zone}/cameras/{camera_id}` | カメラ位置・FOV 更新 (Layer 2) |
| GET | `/spaces/{zone}/live` | ライブ検出 (Layer 3) |
| GET | `/spaces/{zone}/heatmap` | ヒートマップ (Layer 3) `?period=hour\|day\|week` |
| DELETE | `/spaces/{zone}/devices/{id}/override` | DB オーバーライド削除 (YAML に戻す) |
| DELETE | `/spaces/{zone}/cameras/{id}/override` | 同上 (カメラ) |

#### Legacy Spatial API (`routers/spatial.py` — backward-compatible)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sensors/spatial/config` | Building layout, zones, devices, cameras (Layer 1+2) |
| GET | `/sensors/spatial/live` | Real-time person/object positions (Layer 3) |
| GET | `/sensors/spatial/heatmap` | Heatmap data for zones (Layer 3) |

#### Device & Camera Position API (`routers/devices.py` — backward-compatible)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/devices/positions/` | List all device positions (DB only) |
| POST | `/devices/positions/` | Create device position |
| PUT | `/devices/positions/{device_id}` | Update device position |
| DELETE | `/devices/positions/{device_id}` | Delete device position |
| GET | `/devices/cameras/` | List camera position overrides (DB only) |
| PUT | `/devices/cameras/{camera_id}` | Upsert camera position override |
| DELETE | `/devices/cameras/{camera_id}` | Remove camera override (revert to YAML) |

### Voice Service API (`services/voice/src/`)

| Endpoint | Purpose |
|----------|---------|
| `POST /api/voice/synthesize` | Direct text→speech (used by `speak` tool / accept) |
| `POST /api/voice/announce` | Task announcement with LLM text generation |
| `POST /api/voice/announce_with_completion` | Dual voice: announcement + completion |
| `POST /api/voice/feedback/{type}` | Acknowledgment messages |
| `GET /api/voice/rejection/random` | Random pre-generated rejection voice from stock |
| `GET /api/voice/rejection/status` | Rejection stock count / generation status |
| `POST /api/voice/rejection/clear` | Clear and regenerate rejection stock |
| `GET /api/voice/acceptance/random` | Random pre-generated acceptance voice from stock |
| `GET /api/voice/acceptance/status` | Acceptance stock count / generation status |
| `POST /api/voice/acceptance/clear` | Clear and regenerate acceptance stock |
| `GET /api/voice/currency-units/status` | Currency unit name stock status + sample |
| `POST /api/voice/currency-units/clear` | Clear currency unit stock and force regeneration |
| `GET /audio/{filename}` | Serve generated MP3 files |
| `GET /audio/rejections/{filename}` | Serve rejection stock audio files |
| `GET /audio/acceptances/{filename}` | Serve acceptance stock audio files |

VOICEVOX speaker ID 47 (ナースロボ_タイプT). `rejection_stock.py` pre-generates up to 100 rejection voices during idle time (LLM text gen + VOICEVOX synthesis). `acceptance_stock.py` pre-generates up to 50 acceptance voices. `currency_unit_stock.py` pre-generates humorous currency unit names (text only, max 50) for randomized task announcements.

### Wallet Service API (`services/wallet/src/`)

Double-entry credit ledger with PostgreSQL (asyncpg). Key models: `Wallet` (balance), `LedgerEntry` (debit/credit pairs), `Device` (XP tracking), `SupplyStats`. `services/xp_scorer.py` handles dynamic reward multiplier (1.0x-3.0x based on device XP). Swagger UI at `:8003/docs`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/wallets/` | Create wallet |
| GET | `/wallets/{user_id}` | Get balance |
| GET | `/wallets/{user_id}/history` | Transaction history |
| POST | `/transactions/task-reward` | Pay task bounty from system wallet |
| POST | `/transactions/p2p-transfer` | Transfer between users (with fee) |
| GET | `/transactions/transfer-fee` | Preview transfer fee |
| GET | `/transactions/{transaction_id}` | Transaction details |
| POST | `/devices/` | Register device |
| GET | `/devices/` | List devices |
| PUT | `/devices/{device_id}` | Update device metadata |
| POST | `/devices/xp-grant` | Grant XP to all devices in zone |
| POST | `/devices/{device_id}/heartbeat` | Record heartbeat, grant infra reward |
| POST | `/devices/{device_id}/utility-score` | Update device utility score |
| GET | `/devices/zone-multiplier/{zone}` | Get reward multiplier for zone |
| POST | `/devices/{device_id}/funding/open` | Open device funding (list shares) |
| POST | `/devices/{device_id}/funding/close` | Close device funding |
| POST | `/devices/{device_id}/stakes/buy` | Buy device shares |
| POST | `/devices/{device_id}/stakes/return` | Return device shares |
| GET | `/devices/{device_id}/stakes` | List device stakeholders |
| GET | `/users/{user_id}/portfolio` | User's stakes across all devices |
| GET | `/supply` | Supply stats (issued/burned/circulating) |
| POST | `/demurrage/trigger` | Manually trigger demurrage cycle |
| GET | `/reward-rates` | List all reward rates |
| PUT | `/reward-rates/{device_type}` | Update reward rate for device type |
| POST | `/admin/pools` | Create funding pool |
| GET | `/admin/pools` | List all pools (admin) |
| GET | `/admin/pools/{pool_id}` | Pool details with contributions |
| POST | `/admin/pools/{pool_id}/contribute` | Record cash contribution |
| POST | `/admin/pools/{pool_id}/activate` | Activate pool (link device) |
| GET | `/pools` | List public pools (open/funded/active) |

### Mock Infrastructure (`infra/`)

- `mock_llm/` — Keyword-based LLM simulator (FastAPI, OpenAI-compatible). Dual-mode: when `tools` present in request → generates tool calls (Brain mode); when absent → generates natural text (Voice text gen mode). Matches temperature/CO2/supply keywords → tool calls. Also handles currency unit name generation requests
- `virtual_edge/` — Virtual ESP32 device emulator for testing without hardware
- `virtual_camera/` — RTSP server (mediamtx + ffmpeg) for virtual camera feed
- `docker-compose.edge-mock.yml` — Lightweight compose for virtual-edge + mock-llm + virtual-camera

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy (async), paho-mqtt >=2.0, Pydantic 2.x, loguru
- **Frontend**: React 19, TypeScript, Vite 7, Tailwind CSS 4, TanStack Query 5, Framer Motion, Lucide icons; pnpm as package manager
- **ML/Vision**: Python 3.10 (ROCm base image), Ultralytics YOLOv11 (yolo11s.pt + yolo11s-pose.pt), OpenCV, PyTorch (ROCm)
- **LLM**: Ollama with ROCm for AMD GPUs (Qwen2.5 target model)
- **TTS**: VOICEVOX (Japanese speech synthesis)
- **Edge**: MicroPython on ESP32 (BME680, MH-Z19 CO2, DHT22), PlatformIO C++ for camera nodes
- **Infra**: Docker Compose, Mosquitto MQTT, PostgreSQL 16 (asyncpg), nginx

## Code Conventions

- All Python I/O uses `async/await` (asyncio event loop)
- Configuration via environment variables (`.env` file, `python-dotenv`)
- LLM tools follow OpenAI function-calling schema with explicit `parameters.properties` and `required` fields
- Source code is bind-mounted into containers (`volumes: - ../services/X/src:/app`), so changes take effect on container restart without rebuild
- Documentation is bilingual (English code/comments, Japanese deployment docs and tool descriptions)
- Perception monitors are YAML-configured (`services/perception/config/monitors.yaml`), not hardcoded
- Logging uses `loguru` (brain, voice) and standard `logging` (world_model, perception)

## Parallel Development

When working as one of multiple concurrent Claude Code workers, read these documents BEFORE starting:

- `docs/parallel-dev/WORKER_GUIDE.md` — Lane definitions, file ownership, git workflow
- `docs/parallel-dev/API_CONTRACTS.md` — Inter-service API contracts and mocking guidance

### Worktree (必須)

並行開発では **git worktree** を使用する。メインディレクトリ (`Office_as_AI_ToyBox`) で `git checkout` を実行してはならない。

```
/home/sin/code/Office_as_AI_ToyBox     → main (監視・統合専用)
/home/sin/code/soms-worktrees/L{N}     → lane/L{N}-* (各ワーカーの作業用)
```

ワーカー起動時は自分のレーンの worktree パスを working directory に指定すること。

## Environment Configuration

Key variables in `.env` (see `env.example`):

- `LLM_API_URL` — `http://mock-llm:8000/v1` (dev) or `http://ollama:11434/v1` (Docker内部) or `http://host.docker.internal:11434/v1` (ホストOllama)
- `LLM_MODEL` — Model name for Ollama (e.g. `qwen2.5:14b`)
- `MQTT_BROKER` / `MQTT_PORT` — Broker address (default: `mosquitto:1883`)
- `MQTT_USER` / `MQTT_PASS` — MQTT credentials (default: `soms` / `soms_dev_mqtt`)
- `DATABASE_URL` — `postgresql+asyncpg://user:pass@postgres:5432/soms` (Docker)
- `POSTGRES_USER` / `POSTGRES_PASSWORD` — PostgreSQL credentials (default: `soms` / `soms_dev_password`)
- `RTSP_URL` — Camera feed URL (dev: `rtsp://virtual-camera:8554/live`)
- `JWT_SECRET` — Shared JWT signing secret (auth/wallet/dashboard, default: `soms_dev_jwt_secret_change_me`)
- `SLACK_CLIENT_ID` / `SLACK_CLIENT_SECRET` — Slack OAuth app credentials
- `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` — GitHub OAuth app credentials
- `AUTH_BASE_URL` — Auth service public URL for OAuth callbacks (default: `https://localhost:8443/api/auth`)
- `FRONTEND_URL` — Wallet-app URL for post-auth redirect (default: `https://localhost:8443`)
- `TZ` — Timezone (default: `Asia/Tokyo`)
- `HSA_OVERRIDE_GFX_VERSION` — AMD GPU compatibility override (e.g. `12.0.1` for RDNA4)
