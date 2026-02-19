# SOMS 実装状態レポート

**更新日**: 2026-02-20
**ブランチ**: `main` (HEAD: `a0a3fc0`)

---

## 全体サマリー

| カテゴリ | ファイル数 | 行数 | 状態 |
|----------|-----------|------|------|
| Brain (LLM決定エンジン) | 26 .py | ~4,800 | 完成 (Event Store + WalletBridge + DeviceTrust 統合済み) |
| Voice (音声合成) | 6 .py | 1,212 | 完成 (通貨単位ストック追加) |
| Perception (画像認識) | 19 .py | ~1,700 | 完成 |
| Dashboard Backend | 19 .py | 2,062 | 完成 (Sensor API + Spatial API + Device Position API 追加) |
| Dashboard Frontend | 21 .tsx/.ts | ~1,200 | 完成 (TanStack Query 移行済み、fetchTasks ガード追加) |
| Wallet (クレジット経済) | 18 .py | 2,523 | 完成 (Phase 1.5 出資モデル追加) |
| Wallet App (PWA) | 17 .tsx/.ts | ~1,100 | 完成 (出資UI追加) |
| Edge Firmware (Python) | 43 .py | ~2,800 | 完成 |
| Edge Firmware (C++) | 4 .cpp/.h | ~817 | 完成 |
| Edge Enclosure | OpenSCAD + STL | — | v1 完成 (BME680 + PIR バリアント) |
| Tools | 1 .py | ~1,050 | DXF→YAML フロアプランインポーター |
| Infra/テスト | 31 .py | ~4,000 | 完成 |
| **合計** | **~210** | **~24,300** | |

---

## 1. Brain Service (`services/brain/`)

**役割**: LLM駆動の意思決定エンジン。ReAct (Think→Act→Observe) 認知ループ。

### コアモジュール

| ファイル | 行数 | 役割 | 主要クラス/関数 |
|---------|------|------|---------------|
| `src/main.py` | 559 | メインオーケストレータ | `Brain` — MQTT受信、認知ループ(max 5反復)、30秒ポーリング+イベント駆動 |
| `src/llm_client.py` | 156 | LLM API通信 | `LLMClient` — OpenAI互換async wrapper、120秒タイムアウト |
| `src/tool_registry.py` | 149 | ツール定義(6種) | `get_tools()` — create_task, send_device_command, get_zone_status, speak, get_active_tasks, get_device_status |
| `src/tool_executor.py` | 237 | ツール実行ルーター | `ToolExecutor` — sanitizer経由のバリデーション + 各ツールハンドラ |
| `src/mcp_bridge.py` | 64 | MQTT⇔JSON-RPC変換 | `MCPBridge` — asyncio.Futureベースの要求応答相関、10秒タイムアウト |
| `src/sanitizer.py` | 128 | 入力バリデーション | `Sanitizer` — 温度18-28℃、ポンプ最大60秒、タスク作成10件/時間、speak 300秒クールダウン |
| `src/system_prompt.py` | 72 | 憲法AI系プロンプト | `SYSTEM_PROMPT` — 安全第一/コスト意識/重複防止/段階的アプローチ/プライバシー/デバイスネットワーク管理 |
| `src/dashboard_client.py` | 186 | タスク管理REST | `DashboardClient` — タスクCRUD + 二重音声生成(announce + completion) |
| `src/task_reminder.py` | 193 | リマインダー | `TaskReminder` — 1時間後再アナウンス、30分クールダウン、5分チェック間隔 |
| `src/device_registry.py` | ~391 | デバイス状態管理 | `DeviceRegistry` — 適応型タイムアウト、ユーティリティスコア、ネットワークトポロジ追跡、**デバイス信頼メカニズム** |
| `src/wallet_bridge.py` | 71 | Wallet中継 | `WalletBridge` — MQTTハートビート→Wallet REST転送、300秒スロットル |
| `src/spatial_config.py` | 119 | 空間設定 | `SpatialConfig` — オフィスレイアウト、ゾーン・デバイス位置読み込み |
| `src/federation_config.py` | 78 | 連邦設定 | `FederationConfig` — リージョンID設定読み込み |

### デバイス信頼メカニズム (Device Trust)

デバイスが累計1時間のオンライン稼働を経て「信頼済み」に昇格。未確認デバイスはLLMコンテキストから除外される。

- **信頼閾値**: 3600秒 (累計オンライン時間)
- **LLMフィルタリング**: `get_status_summary()` / `get_device_tree()` で未確認デバイスを1行にまとめて表示
- **システムプロンプト統合**: 未確認デバイスへの調査タスク作成を抑制する指示

### WorldModel モジュール (`src/world_model/`)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `world_model.py` | 742 | ゾーン統一状態管理、MQTTトピック解析、8種イベント検知(CO2超過/温度急変/長時間座位/ドア開閉等) |
| `data_classes.py` | 203 | Pydanticモデル5種: EnvironmentData, OccupancyData, DeviceState, Event, ZoneState |
| `sensor_fusion.py` | 65 | 指数減衰重み付けセンサーフュージョン (温度半減期2分、CO2 1分、在室30秒) |

### Event Store モジュール (`src/event_store/`)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `writer.py` | 196 | `EventWriter` — 非同期バッファ (10秒 or 100件でフラッシュ) |
| `aggregator.py` | 348 | `HourlyAggregator` — 毎時集計 (count, avg, min, max) |
| `models.py` | 70 | SQLAlchemy テーブル定義 (raw_events, hourly_aggregates) |
| `database.py` | 123 | async engine + session factory |

### Task Scheduling モジュール (`src/task_scheduling/`)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `queue_manager.py` | 194 | 最小ヒープタスクキュー、24時間で強制ディスパッチ |
| `decision.py` | 105 | ディスパッチ判定: 緊急度/ゾーン活動/在室人数/時間帯/集中度 |
| `priority.py` | 70 | 優先度計算: urgency×1000 + 待機時間 + 締切ボーナス |

### 設計パターン
- **ReAct Loop**: Think→Act→Observe、最大5反復/サイクル
- **Hybrid Scheduling**: MQTTイベント駆動 (3秒バッチ遅延) + 30秒ポーリング
- **Dual Voice**: タスク作成時にannouncement + completion音声を事前生成
- **Duplicate Prevention**: アクティブタスク一覧をLLMコンテキストに注入
- **Device Trust**: 累計1時間稼働で信頼昇格、未確認デバイスをLLMコンテキストから除外

---

## 2. Voice Service (`services/voice/`)

**役割**: VOICEVOX経由の日本語音声合成 + LLMテキスト生成。

| ファイル | 行数 | 役割 |
|---------|------|------|
| `src/main.py` | 385 | FastAPI エンドポイント13種 |
| `src/speech_generator.py` | 325 | VOICEVOX合成パイプライン (speaker_id=47, ナースロボ_タイプT) + 通貨単位名生成 |
| `src/voicevox_client.py` | 105 | VOICEVOX REST APIクライアント (4スピーカーバリアント: normal/cool/happy/whisper) |
| `src/models.py` | 40 | Pydanticリクエスト/レスポンスモデル |
| `src/rejection_stock.py` | 208 | リジェクション音声事前生成 (max 100、アイドル時LLM+VOICEVOX) |
| `src/currency_unit_stock.py` | 149 | 通貨単位名ストック (テキストのみ、max 50、アイドル時LLM生成) |

### エンドポイント

| メソッド | パス | 用途 |
|---------|------|------|
| POST | `/api/voice/synthesize` | テキスト→音声直接合成 (speakツール/受諾) |
| POST | `/api/voice/announce` | タスクアナウンス (LLMテキスト生成 + 合成) |
| POST | `/api/voice/announce_with_completion` | 二重音声: アナウンス + 完了メッセージ |
| POST | `/api/voice/feedback/{type}` | 確認メッセージ |
| GET | `/api/voice/rejection/random` | ストックからランダムリジェクション音声 |
| GET | `/api/voice/rejection/status` | ストック状況 |
| POST | `/api/voice/rejection/clear` | ストック再生成 |
| GET | `/api/voice/currency-units/status` | 通貨単位ストック状況 + サンプル |
| POST | `/api/voice/currency-units/clear` | 通貨単位ストック再生成 |
| GET | `/audio/{filename}` | 生成済みMP3配信 |
| GET | `/audio/rejections/{filename}` | リジェクション音声配信 |

---

## 3. Perception Service (`services/perception/`)

**役割**: YOLOv11ベースのコンピュータビジョン。カメラ自動発見、在室検知、活動分析。

### コアモジュール

| モジュール | ファイル数 | 主要クラス |
|-----------|-----------|-----------|
| `monitors/` | 4 | `MonitorBase`, `OccupancyMonitor`, `WhiteboardMonitor`, `ActivityMonitor` |
| `image_sources/` | 5 | `ImageSourceFactory`, `RtspSource`, `HttpStreamSource`, `MqttImageSource`, `CameraInfo` |
| (ルート) | ~6 | `main.py`, `camera_discovery.py`, `pose_estimator.py`, `activity_analyzer.py`, `yolo_inference.py` |

### 機能

- **カメラ自動発見**: 非同期TCPポートスキャン + URLプローブ + YOLO検証 (192.168.128.0/24)
- **在室モニタ**: YOLO物体検知 → 人数カウント → MQTT publish
- **ホワイトボード**: 変化検知 → キャプチャ
- **活動分析**: 4段ティアードバッファ (最大4時間)、姿勢正規化、長時間座位検知
- **ポーズ推定**: YOLO11s-pose → 17キーポイント

---

## 4. Dashboard Service (`services/dashboard/`)

### Backend (FastAPI + SQLAlchemy async + PostgreSQL)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `backend/main.py` | 77 | FastAPIアプリ初期化、CORS、6ルーター登録 |
| `backend/database.py` | 13 | PostgreSQL (asyncpg) 非同期エンジン |
| `backend/models.py` | 88 | SQLAlchemyモデル: Task(27列), VoiceEvent, SystemStats, User |
| `backend/schemas.py` | 118 | Pydantic 2.xスキーマ (TaskCreate/Update/Accept, UserBase, etc.) |
| `backend/sensor_schemas.py` | 50 | センサーデータ用Pydanticスキーマ |
| `backend/spatial_config.py` | 114 | 空間設定・フロアプラン読み込み |
| `backend/routers/tasks.py` | 414 | タスクCRUD: 2段階重複検知、受諾/完了/リマインダー/キュー管理、wallet連携 |
| `backend/routers/users.py` | 78 | ユーザーCRUD (list/get/create/update) — AsyncSession実装 |
| `backend/routers/voice_events.py` | 47 | speakツール用エフェメラルイベント記録 (60秒ポーリング) |
| `backend/routers/sensors.py` | 135 | センサーデータAPI (latest/time-series/zones/events/llm-activity) |
| `backend/routers/spatial.py` | 106 | 空間API (config/live/heatmap) |
| `backend/routers/devices.py` | 141 | デバイス位置管理API (CRUD) |
| `backend/repositories/` | 681 | Repositoryパターン: SensorDataRepository + SpatialDataRepository (ABC + PgSQL実装 + DI) |

### Frontend (React 19 + TypeScript + Vite 7 + Tailwind CSS 4)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `src/App.tsx` | 340 | メインダッシュボード: 3カラムグリッド、TanStack Query (5秒/3秒ポーリング) |
| `src/api.ts` | — | API クライアント (Array.isArray ガード付き) |
| `src/components/TaskCard.tsx` | 153 | タスクカード: 受諾→対応中→完了のステート遷移、urgencyカラー |
| `src/components/UserSelector.tsx` | 50 | ユーザー選択ドロップダウン |
| `src/components/WalletBadge.tsx` | 39 | クレジット残高バッジ (10秒ポーリング) |
| `src/components/WalletPanel.tsx` | 60 | 取引履歴サイドパネル |
| `src/audio/AudioQueue.ts` | 141 | 優先度付き音声キュー (USER_ACTION > ANNOUNCEMENT > VOICE_EVENT、max 20) |

---

## 5. Wallet Service (`services/wallet/`)

**役割**: 複式簿記クレジット経済。タスク報酬、デバイスXP、出資モデル。

| ファイル | 行数 | 役割 |
|---------|------|------|
| `src/main.py` | 108 | FastAPIアプリ、起動時DB初期化 + system wallet自動作成 + 6ルーター登録 |
| `src/database.py` | 17 | PostgreSQL (asyncpg) 非同期エンジン |
| `src/models.py` | 153 | Wallet, LedgerEntry, Device, DeviceStake, FundingPool, PoolContribution, SupplyStats, RewardRate |
| `src/schemas.py` | 308 | Pydanticスキーマ (15+種: Transaction, Wallet, Device, Stake, Pool, etc.) |
| `src/services/ledger.py` | 229 | `transfer()`: 複式仕訳、冪等性 (reference_id)、デッドロック防止 (ID順ロック) |
| `src/services/xp_scorer.py` | 162 | ゾーンデバイスXP付与、動的報酬乗数 (1.0x-3.0x)、貢献度重み付け |
| `src/services/stake_service.py` | 338 | デバイス出資: open/close/buy/return/distribute_reward |
| `src/services/pool_service.py` | 210 | プール出資: create/contribute/activate (shares一括割当) |
| `src/services/demurrage.py` | 59 | デマレッジ (保有税) サイクル |
| `src/services/monetary_policy.py` | 50 | 金融政策パラメータ |
| `src/routers/wallets.py` | 45 | 残高照会、ウォレット作成 |
| `src/routers/transactions.py` | 156 | 取引履歴、タスク報酬API、P2P送金、手数料プレビュー |
| `src/routers/devices.py` | 208 | デバイス登録/一覧/ハートビート(比例配分)/XP付与/utility-score |
| `src/routers/stakes.py` | 205 | Model A: SOMS出資 6EP + portfolio |
| `src/routers/pools.py` | 202 | Model B: プール出資 admin 5EP + public 1EP |
| `src/routers/admin.py` | 73 | 供給統計、デマレッジ、報酬レート |

---

## 6. Edge Firmware (`edge/`)

### SensorSwarm (Hub + Leaf 2階層)

| ディレクトリ | 言語 | 役割 |
|-------------|------|------|
| `edge/lib/swarm/` | MicroPython | 共有ライブラリ: message.py (バイナリプロトコル), hub.py, leaf.py, transport_*.py |
| `edge/swarm/hub-node/` | MicroPython | Hub: WiFi+MQTT→クラウド、ESP-NOW/UART/I2C→Leaf群 |
| `edge/swarm/leaf-espnow/` | MicroPython | Leaf (ESP-NOW): ESP32-C6 用 |
| `edge/swarm/leaf-uart/` | MicroPython | Leaf (UART): Raspberry Pi Pico 用 |
| `edge/swarm/leaf-arduino/` | C++ (PlatformIO) | Leaf (I2C): ATtiny85/84 用 (<2KB RAM) |

### センサーノード筐体 (`edge/enclosure/sensor-node-v1/`)

3Dプリント筐体 (OpenSCAD パラメトリック設計)。2チャンバー式熱分離構造。

| 項目 | 内容 |
|------|------|
| ターゲット | XIAO ESP32-C6 + BME680 + MH-Z19C |
| バリアント | PIR (AM312/HC-SR501) / ブランクキャップ / ファン有無 |
| 寸法 | 55.2 × 33.2 × 50.2 mm (ファンなし) |
| 設計 | 上部MCU室 + 下部センサー室、3mm+5mmエアギャップ断熱 |
| コネクタ | JST-XH 8P チャンバー間ハーネス |

### レガシーファームウェア

| ディレクトリ | 内容 |
|-------------|------|
| `edge/office/unified-node/` | 設定駆動型汎用ファームウェア (config.json) |
| `edge/office/sensor-02/` | BME680/MH-Z19Cドライバー |
| `edge/test-edge/camera-node/` | PlatformIO C++ カメラノード |
| `edge/test-edge/sensor-node/` | PlatformIO C++ センサーノード |

### 診断ツール (`edge/tools/`)
`blink_identify.py`, `diag_i2c.py`, `test_uart.py`, `clean_scan.py` 等17スクリプト

---

## 7. Tools (`tools/`)

### DXF フロアプランインポーター (`tools/import_floorplan.py`)

AutoCAD DXF/DWG ファイルを `config/spatial.yaml` に変換するスタンドアロンスクリプト。

| 機能 | 内容 |
|------|------|
| レイヤー検査 | DXF レイヤー一覧とエンティティ数の表示 |
| ポリゴン抽出 | 閉じた LWPOLYLINE からゾーンポリゴンを抽出 |
| テキスト関連付け | ポリゴン内のテキストラベルを部屋名として関連付け |
| 隣接グラフ | ゾーン間の隣接関係を自動計算 |
| SVG プレビュー | フロアプラン可視化用 SVG 生成 |

現在のフロアプラン: GITY Office (29.3m × 20.1m, 9ゾーン, 8デバイス, 3カメラ)

---

## 8. Infrastructure (`infra/`)

### Docker Compose

| ファイル | サービス数 | 用途 |
|---------|-----------|------|
| `docker-compose.yml` | 12 | 本番構成: mosquitto, brain, postgres, backend, frontend, voicevox, voice-service, wallet, wallet-app, ollama, mock-llm, perception |
| `docker-compose.edge-mock.yml` | 3 | 仮想構成: virtual-edge + mock-llm + virtual-camera |

### サービスポート

| サービス | ポート | コンテナ名 |
|---------|--------|-----------|
| Dashboard Frontend (nginx) | 80 | soms-frontend |
| Dashboard Backend API | 8000 | soms-backend |
| Mock LLM | 8001 | soms-mock-llm |
| Voice Service | 8002 | soms-voice |
| Wallet Service | 127.0.0.1:8003 | soms-wallet |
| Wallet App (PWA) | 8004 | soms-wallet-app |
| PostgreSQL | 127.0.0.1:5432 | soms-postgres |
| VOICEVOX Engine | 50021 | soms-voicevox |
| Ollama (LLM) | 11434 | soms-ollama |
| MQTT Broker | 1883 (TCP) / 9001 (WS) | soms-mqtt |

---

## 9. 直近コミット履歴

```
a0a3fc0 docs: sync documentation with device trust, spatial map, and enclosure features
ca517e1 feat: add sensor node enclosure v1 (BME680 + PIR variants)
4cd7272 feat: import real office floor plan from DXF
5bc6151 fix: guard against non-array API response in fetchTasks
29f2b00 feat: add device trust mechanism to filter unverified devices from LLM context
bdfabfc feat: add federation Phase 1 region identity to all services
4101019 feat: add sensor visualization and device placement GUI on floor plan
352c88c feat: add spatial map service with floor plan visualization
bad0cac feat: add sensor API repository pattern, HEMS character configs
cfffaf1 feat: introduce TanStack Query, migrate to pnpm, add hadolint
```

---

## 10. 既知の問題・改善候補

| 優先度 | 項目 | 詳細 |
|--------|------|------|
| 中 | 受諾音声レイテンシ | ストック化されていない (1-2秒遅延) |
| 中 | バッテリー監視UI | SwarmHub 状態の可視化 |
| 中 | Event Store ダッシュボード | hourly_aggregates をグラフ表示 |
| 中 | 24h 安定稼働テスト | Phase 0 完了判定の最終条件 |
| 低 | 認証なし | nginx/API層に認証レイヤーなし (PoC段階) |
| 低 | フロントエンドエラーバウンダリ | 未実装 |

---

## 11. アーキテクチャ図

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
                    │  DeviceTrust      │
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
┌──────────────┐    ┌──────────────┐
│  Edge Devices │    │  Perception  │
│  SwarmHub +   │    │  YOLOv11     │
│  Leaf nodes   │    │  Monitors    │
│  MCP/JSON-RPC │    │  (ROCm GPU)  │
└──────────────┘    └──────────────┘
```

---

## 12. 技術スタック

| レイヤー | 技術 |
|---------|------|
| **LLM** | Ollama + qwen2.5:14b (Q4_K_M), ROCm (AMD RX 9700 RDNA4) |
| **Backend** | Python 3.11, FastAPI, SQLAlchemy (async), asyncpg, paho-mqtt >=2.0, Pydantic 2.x, loguru |
| **Frontend** | React 19, TypeScript 5.9, Vite 7, Tailwind CSS 4, TanStack Query 5, Framer Motion 12, Lucide Icons; pnpm |
| **Vision** | Python 3.10 (ROCm base), Ultralytics YOLOv11 (yolo11s.pt + yolo11s-pose.pt), OpenCV, PyTorch (ROCm) |
| **TTS** | VOICEVOX (speaker_id=47, ナースロボ_タイプT) |
| **Edge** | MicroPython (ESP32/Pico), PlatformIO C++ (ATtiny/ESP32-CAM) |
| **Hardware** | OpenSCAD (筐体パラメトリック設計), ezdxf/shapely (フロアプラン変換) |
| **Infra** | Docker Compose, Mosquitto MQTT, PostgreSQL 16 (asyncpg), nginx |
| **通信** | MQTT (テレメトリ), MCP/JSON-RPC 2.0 (デバイス制御), REST (サービス間) |
