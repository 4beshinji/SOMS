# SOMS — 都市をAI化するアーキテクチャの実証

**Symbiotic Office Management System**

分散型ローカルLLMによる自律的空間管理。1つのオフィスから都市全体へスケールする Core Hub アーキテクチャの Phase 0 実装。

センサーデータとカメラ映像をもとにローカルLLMがリアルタイムで自律判断し、APIで操作できない物理タスクは人間に経済的インセンティブで委託する。全処理がGPUサーバー1台で完結し、生データは一切クラウドに送信しない (50,000:1 のデータ圧縮)。

## Core Hub ビジョン

```
                      ┌──────────────────┐
                      │   City Data Hub  │ 集約統計のみ受信 (~1MB/Hub/日)
                      └────────┬─────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
        │  Office   │   │   Farm    │   │   Home    │
        │  Hub      │   │   Hub     │   │   Hub     │
        │  (SOMS)   │   │ (auto_JA) │   │  (HEMS)   │
        └───────────┘   └───────────┘   └───────────┘
         Phase 0 実装     同一アーキテクチャ、異なるプロンプトとセンサー
```

各 Core Hub は独立したローカルLLM+GPUを持ち、ネットワーク切断時も自律動作を継続する。システムプロンプト（行動原則）とセンサー構成の差し替えでオフィス・農場・住宅に展開可能。

同一アーキテクチャから以下のドメイン特化システムが派生:

- **[auto_JA](../auto_JA/)** — IoT農業・養殖管理（水耕栽培環境制御 + 養蜂モニタリング・分蜂検知）
- **[HEMS](../hems/)** — 独居者向けパーソナルAI（AIキャラクターシステム + スマートホーム制御）

## Features

- **自律環境制御** — センサー → LLM → デバイス制御の30秒認知サイクル（ReAct 5イテレーション、3層安全機構）
- **物理タスク委託** — APIで操作不能な作業を人間にクレジット報酬で委託、ダッシュボードで受諾・完了
- **コンピュータビジョン** — YOLOv11 による在室検知、活動分析、転倒検知、MTMC多カメラ人物追跡
- **クレジット経済** — 複式簿記台帳、デバイスXP・動的報酬乗数、デマレッジ2%/日、P2P送金、デバイス投資
- **音声合成** — VOICEVOX による日本語タスク通知・応答（事前生成ストック方式）
- **SensorSwarm** — ESP32 Hub+Leaf 2層センサーネットワーク（ESP-NOW / UART / I2C / BLE）
- **SwitchBot連携** — クラウドAPI v1.1 経由で9種のデバイスをMQTT統合
- **OAuth認証** — Slack / GitHub ログイン + JWT トークン（共有シークレット方式）
- **空間管理** — フロアプラン可視化、デバイス配置編集、ライブ検出、ヒートマップ（Admin UI）
- **モバイルウォレット** — PWA: 残高確認、QRスキャン、P2P送金、デバイス投資ポートフォリオ

## アーキテクチャ

```
                ┌──────────────────┐
                │   Ollama / LLM   │
                │  (qwen2.5:14b)   │
                └────────┬─────────┘
                         │ OpenAI API
                ┌────────┴─────────┐
                │   Brain Service   │
                │  ReAct Loop (5x)  │
                │  WorldModel       │
                │  TaskScheduling   │
                └──┬───┬───┬───┬───┘
                   │   │   │   │
        ┌──────────┘   │   │   └──────────┐
        ▼              ▼   ▼              ▼
┌──────────────┐ ┌─────────────┐ ┌──────────────┐
│ MQTT Broker  │ │  Dashboard  │ │Voice Service │
│ (Mosquitto)  │ │  Backend    │ │  + VOICEVOX  │
└──┬───┬───────┘ │  (FastAPI)  │ └──────────────┘
   │   │         └──────┬──────┘
   │   │                │
   │   │         ┌──────┴──────┐
   │   │         │  Dashboard  │
   │   │         │  Frontend   │◄── nginx ──► Wallet
   │   │         │  (React 19) │              Service
   │   │         └─────────────┘
   │   │
   │   └─────────────────┐
   ▼                     ▼
┌──────────────┐  ┌──────────────┐
│ Edge Devices │  │  Perception  │
│ SensorSwarm  │  │  YOLOv11     │
│ Hub + Leaf   │  │  Monitors    │
│ MCP/JSON-RPC │  │  (ROCm GPU)  │
└──────────────┘  └──────────────┘
```

| Layer | Directory | Description |
|-------|-----------|-------------|
| Central Intelligence | `services/brain/` | LLM-driven ReAct 認知ループ (Think→Act→Observe, 6ツール, 3層安全機構) |
| Perception | `services/perception/` | YOLOv11 — 在室検知, ホワイトボード, 活動分析, MTMC人物追跡 |
| Communication | MQTT (Mosquitto) | MCP over MQTT — JSON-RPC 2.0 でエッジデバイスを直接制御 |
| Edge | `edge/` | SensorSwarm Hub-Leaf 2層ネットワーク (ESP-NOW/UART/I2C/BLE) |
| Human Interface | `services/dashboard/`, `services/voice/` | キオスクダッシュボード + VOICEVOX 音声合成 + モバイルウォレットPWA |
| Economy | `services/wallet/` | 複式簿記クレジット台帳 (デバイスXP, デマレッジ2%/日, 焼却5%) |

## Services

| Service | Port | Container |
|---------|------|-----------|
| Dashboard Frontend (nginx) | 80 | soms-frontend |
| Admin Frontend | 8007 | soms-admin |
| Dashboard Backend API | 8000 | soms-backend |
| Mock LLM | 8001 | soms-mock-llm |
| Voice Service | 8002 | soms-voice |
| Wallet Service | 127.0.0.1:8003 | soms-wallet |
| Wallet App (PWA) | 8004 (HTTPS: 8443) | soms-wallet-app |
| SwitchBot Bridge | 8005 | soms-switchbot |
| Auth Service | 127.0.0.1:8006 | soms-auth |
| PostgreSQL | 127.0.0.1:5432 | soms-postgres |
| VOICEVOX Engine | 50021 | soms-voicevox |
| Ollama (LLM) | 11434 | soms-ollama |
| MQTT Broker | 1883 | soms-mqtt |

## Quick Start

### 前提条件

- Docker Engine 24+ および Docker Compose v2

### 起動手順

```bash
# 1. Clone and configure
git clone <repository_url>
cd Office_as_AI_ToyBox
cp env.example .env

# 2. Full simulation (no GPU/hardware required)
./infra/scripts/start_virtual_edge.sh

# 3. Production (AMD ROCm GPU + real hardware)
docker compose -f infra/docker-compose.yml up -d --build
```

### 動作確認

```bash
# Dashboard Backend API
curl http://localhost:8000/health

# MQTT sensor data
docker exec soms-mqtt mosquitto_sub -u soms -P soms_dev_mqtt -t 'office/#' -v
```

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed setup.

## Testing

**746 unit tests** across 7 services (no running services required):

```bash
for d in services/brain/tests services/auth/tests services/voice/tests \
  services/dashboard/backend/tests services/wallet/tests \
  services/switchbot/tests services/perception/tests; do
  .venv/bin/python -m pytest "$d" --tb=short
done
```

| Service | Tests |
|---------|-------|
| Brain | 189 |
| Dashboard Backend | 172 |
| Auth | 97 |
| Perception | 86 |
| Voice | 79 |
| Wallet | 64 |
| SwitchBot | 59 |

See `CLAUDE.md` for integration tests and per-service commands.

## Tech Stack

- **LLM**: Ollama + Qwen2.5:14b (ROCm, AMD GPU)
- **Backend**: Python 3.11, FastAPI, SQLAlchemy (async), PostgreSQL 16
- **Frontend**: React 19, TypeScript, Vite 7, Tailwind CSS 4
- **Vision**: YOLOv11, OpenCV, PyTorch (ROCm)
- **TTS**: VOICEVOX (Japanese)
- **Edge**: ESP32 MicroPython + SensorSwarm + PlatformIO C++
- **Infra**: Docker Compose (15 services), Mosquitto MQTT, nginx

Python + MQTT による純粋なイベント駆動アーキテクチャ。重量級ミドルウェア不使用。

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [SYSTEM_OVERVIEW.md](docs/SYSTEM_OVERVIEW.md) | 技術仕様 |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | デプロイ手順 |
| [CITY_SCALE_VISION.md](docs/CITY_SCALE_VISION.md) | 都市スケールアーキテクチャ構想 |
| [CURRENCY_SYSTEM.md](docs/CURRENCY_SYSTEM.md) | クレジット経済の設計 |
| [CONTRIBUTING.md](docs/CONTRIBUTING.md) | 開発参加ガイド |
| [architecture/](docs/architecture/) | ADR・詳細設計 (12ドキュメント) |
| [promo/](docs/promo/) | ピッチデッキ・記事・デザイン素材 |
| [CLAUDE.md](CLAUDE.md) | 開発者リファレンス (API仕様, コード規約, テスト詳細) |

## License

See LICENSE file.
