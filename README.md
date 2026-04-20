<p align="center">
  <br />
  <img src="docs/promo/soms-logo-placeholder.svg" width="80" alt="SOMS" />
  <br />
</p>

<h1 align="center">SOMS</h1>

<p align="center">
  <strong>Self-expanding distributed AI that turns physical spaces into intelligent organisms.</strong>
</p>

<p align="center">
  <a href="docs/CITY_SCALE_VISION.md">Vision</a> &middot;
  <a href="docs/DEPLOYMENT.md">Deploy</a> &middot;
  <a href="docs/CONTRIBUTING.md">Contribute</a> &middot;
  <a href="docs/architecture/v2-b2b-migration.md">v2 B2B migration</a> &middot;
  <a href="docs/SYSTEM_OVERVIEW.md">Tech Spec</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/cloud_dependency-zero-black?style=flat-square" alt="cloud" />
  <img src="https://img.shields.io/badge/license-PolyForm_Perimeter_1.0.0-blue?style=flat-square" alt="license" />
</p>

---

> **Your GPU + your sensors = one CoreHub (autonomous intelligence node).**
>
> CoreHubs auto-discover nearby sensors, interpret data with a local LLM,
> dispatch physical tasks to humans, and federate across multiple hubs.
> All raw data stays local.

> **v2 (B2B) note**: the v1 credit economy (wallet, P2P, device XP) was
> removed for employment-relationship deployments. Legacy preserved at
> branch `legacy/v1-with_wallet` / tag `v1.0-with_wallet`.
> See [`docs/architecture/v2-b2b-migration.md`](docs/architecture/v2-b2b-migration.md).

---

## Why

Every "smart city" platform sends your data to someone else's cloud and charges you to read it back. SOMS inverts that:

| Traditional | SOMS |
|-------------|------|
| Data leaves your building | Raw data **never** leaves the node (50,000:1 compression) |
| Cloud LLM, single point of failure | Local LLM per hub, runs offline indefinitely |
| Vendor lock-in, API fees | Open source, deploy anywhere, zero cloud cost |
| Manual task dispatch | LLM watches sensors, dispatches tasks automatically |

## Get Involved

| | What you do |
|-|-------------|
| **Deploy a CoreHub** | Run Docker + GPU — full autonomous AI node for your space |
| **Add sensors** | Plug in ESP32 (~$3) — auto-discovered, integrated instantly |
| **Complete tasks** | Respond to tasks the LLM dispatches through the dashboard |
| **Write code** | Open a PR — deploys to every node |

## Quick Start

```bash
git clone <repository_url> && cd Office_as_AI_ToyBox
cp env.example .env

# Simulation mode  — no GPU, no hardware, just Docker
./infra/scripts/start_virtual_edge.sh

# Production  — AMD ROCm GPU + real sensors
docker compose -f infra/docker-compose.yml up -d --build
```

```bash
# Verify
curl http://localhost:8000/health
docker exec soms-mqtt mosquitto_sub -u soms -P soms_dev_mqtt -t 'office/#' -v
```

> See **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** for full setup instructions.

**Auto-discovery** — CoreHubs actively scan for new devices (TCP probe + YOLO verification) and integrate anything that speaks MQTT `{"value": X}`.

## Architecture

```
              ┌──────────────────────┐
              │    City Data Hub     │  aggregated stats only (~1 MB/hub/day)
              └──────────┬───────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
    ┌─────┴──────┐ ┌────┴─────┐ ┌─────┴──────┐
    │  CoreHub A │ │ CoreHub B│ │  CoreHub C │    ← anyone can run one
    │  LLM+GPU   │ │ LLM+GPU  │ │  LLM+GPU   │
    └─────┬──────┘ └────┬─────┘ └─────┬──────┘
          │              │              │
    ┌──┬──┤        ┌──┬──┤        ┌──┬──┤
    S  S  C        S  C  S        S  S  S         ← anyone can add these
```

### Inside a CoreHub

| Layer | What it does | Implementation |
|-------|-------------|----------------|
| **AI Core** | ReAct cognitive loop — Think / Act / Observe every 30s | `services/brain/` |
| **Perception** | YOLOv11 — occupancy, activity, fall detection, multi-camera tracking | `services/perception/` |
| **Audit trail** | Append-only task lifecycle log (no amounts) | `task_audit_log` in dashboard DB |
| **Edge** | SensorSwarm mesh (ESP-NOW/UART/I2C/BLE) + SwitchBot bridge | `edge/` |
| **Comms** | MQTT message bus — MCP over JSON-RPC 2.0 | Mosquitto |
| **Interface** | Dashboard + VOICEVOX voice + admin console | `services/dashboard/`, `services/voice/`, `services/admin/` |

## Adding a Sensor

No registration. No approval. Just publish:

```bash
mosquitto_pub -h <hub_ip> -u soms -P soms_dev_mqtt \
  -t 'office/my_zone/sensor/my_device/temperature' \
  -m '{"value": 23.5}'
```

The WorldModel picks it up instantly. The LLM starts using it.

For mesh networks without WiFi, use **SensorSwarm** — ESP32 Hub aggregates Leaf nodes over ESP-NOW / UART / I2C / BLE.

## Domain Adaptation

Same software, different sensors and system prompt:

| Domain | Sensors | Example tasks |
|--------|---------|---------------|
| Urban environment | Weather, air quality, cameras | Alerts, inspections |
| Office | Temp, CO2, cameras | Ventilation, cleaning, supplies |
| Agriculture | pH, EC, water temp, light | Nutrient adjustment, harvest |
| Retail | Foot traffic cameras, climate | Restocking, display changes |
| Residential | Environment, security cameras | Elder care, energy saving |

Related projects: **[auto_JA](../auto_JA/)** (IoT agriculture) &middot; **[HEMS](../hems/)** (personal AI + smart home)

## Services

| Service | Port | Container |
|---------|------|-----------|
| Dashboard Frontend | 80 | soms-frontend |
| Dashboard Backend | 8000 | soms-backend |
| Admin Frontend | 80 (path) | soms-admin-frontend |
| Auth Service | 127.0.0.1:8006 | soms-auth |
| Voice + VOICEVOX | 8002 / 50021 | soms-voice / soms-voicevox |
| SwitchBot Bridge | 8005 | soms-switchbot |
| Ollama (LLM) | 11434 | soms-ollama |
| Mock LLM | 8001 | soms-mock-llm |
| MQTT Broker | 1883 | soms-mqtt |
| PostgreSQL | 127.0.0.1:5432 | soms-postgres |

## Testing

Unit tests (no running containers required):

```bash
for d in services/{brain,auth,voice,dashboard/backend,switchbot,zigbee2mqtt-bridge,perception}/tests; do
  .venv/bin/python -m pytest "$d" --tb=short
done
```

| Service | Tests | | Service | Tests |
|---------|-------|-|---------|-------|
| Brain | 333 | | Auth | 82 |
| Dashboard | 221 | | SwitchBot | 59 |
| Voice | 56 | | Zigbee2MQTT | 124 |
| Perception | 196 | | | |

## Tech Stack

| | |
|-|-|
| **LLM** | Ollama + Qwen 2.5 (ROCm / AMD GPU) |
| **Backend** | Python 3.11, FastAPI, SQLAlchemy async, PostgreSQL 16 |
| **Frontend** | React 19, TypeScript, Vite 7, Tailwind CSS 4 |
| **Vision** | YOLOv11, OpenCV, PyTorch (ROCm) |
| **TTS** | VOICEVOX (Japanese speech synthesis) |
| **Edge** | ESP32 MicroPython, SensorSwarm, PlatformIO C++ |
| **Infra** | Docker Compose (15 services), Mosquitto MQTT, nginx |

Pure event-driven architecture on Python + MQTT. No heavyweight middleware.

## Docs

| | |
|-|-|
| **[CITY_SCALE_VISION.md](docs/CITY_SCALE_VISION.md)** | Architecture vision, data sovereignty, self-expansion mechanics |
| **[SYSTEM_OVERVIEW.md](docs/SYSTEM_OVERVIEW.md)** | Full technical specification |
| **[architecture/v2-b2b-migration.md](docs/architecture/v2-b2b-migration.md)** | v1→v2 migration — removing the credit economy |
| **[CONTRIBUTING.md](docs/CONTRIBUTING.md)** | How to participate — code, GPU, sensors |
| **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** | Step-by-step deployment guide |
| **[architecture/](docs/architecture/)** | ADRs & detailed design (12 documents) |
| **[CLAUDE.md](CLAUDE.md)** | Developer reference — APIs, conventions, tests |

## License

SOMS is licensed under the **[PolyForm Perimeter License 1.0.0](LICENSE)**.

You may use, modify, and redistribute SOMS for any purpose, including internal use within an organization, **except for providing a product or service that competes with SOMS**. See the LICENSE file or <https://polyformproject.org/licenses/perimeter/1.0.0/> for the full terms.

The software is provided **as is, without warranty or support obligation**. The licensor is not liable for any damages arising out of its use.
