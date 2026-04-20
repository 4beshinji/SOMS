> ⚠️ **v2 B2B note**: this document predates the v2 fork and may reference the v1 credit economy (wallet, XP, bounty, demurrage). Those features are removed on `main`. See [`docs/architecture/v2-b2b-migration.md`](../architecture/v2-b2b-migration.md) for the current architecture. v1 is preserved at branch `legacy/v1-with_wallet` / tag `v1.0-with_wallet`.

# SOMS 実装状態レポート

**更新日**: 2026-02-25
**ブランチ**: `main` (HEAD: `6e36ef9`)

---

## 全体サマリー

| カテゴリ | ファイル数 | 行数 | 状態 |
|----------|-----------|------|------|
| Brain (LLM決定エンジン) | 26 .py | ~4,850 | 完成 (Event Store + WalletBridge + DeviceTrust + 転倒検知対応 統合済み) |
| Voice (音声合成) | 7 .py | ~1,400 | 完成 (受諾ストック + 通貨単位ストック追加) |
| Perception (画像認識) | 26 .py | ~3,350 | 完成 (MTMC人物追跡 + ArUcoキャリブレーション + 転倒検知追加) |
| Dashboard Backend | 19 .py | 2,210 | 完成 (Sensor API + Spatial API + Device Position API + JWT認証 + LLM Timeline) |
| Dashboard Frontend | 23 .tsx/.ts | ~1,860 | 完成 (TanStack Query、authFetch JWT統合+強制ログアウト、LLM Timeline、デバイス状態監視、占有ヒートマップ、ErrorBoundary) |
| Wallet (クレジット経済) | 18 .py | 2,591 | 完成 (Phase 1.5 出資モデル + JWT認証) |
| Wallet App (PWA) | 23 .tsx/.ts | ~1,850 | 完成 (出資UI + OAuth認証 + HTTPS) |
| Auth (OAuth認証) | 10 .py | 736 | 完成 (Slack + GitHub OAuth, JWT発行) |
| SwitchBot (IoTブリッジ) | 14 .py | 983 | 完成 (Cloud API v1.1, 9デバイスタイプ対応) |
| Edge Firmware (Python) | 43 .py | ~2,800 | 完成 |
| Edge Firmware (C++) | 4 .cpp/.h | ~817 | 完成 |
| Edge Enclosure | OpenSCAD + STL | — | v1 完成 (BME680 + PIR バリアント) |
| Tools | 1 .py | ~1,050 | DXF→YAML フロアプランインポーター |
| Infra/テスト | 32 .py | ~4,300 | 完成 (Docker Smoke Test 追加) |
| ユニットテスト (7サービス) | 50 .py | ~7,550 | 711件 (Brain 167, Dashboard 159, Auth 97, Perception 86, Voice 79, Wallet 64, SwitchBot 59) |
| **合計** | **~287** | **~34,700** | |

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
| `src/system_prompt.py` | 79 | 憲法AI系プロンプト | `SYSTEM_PROMPT` — 安全第一/コスト意識/重複防止/段階的アプローチ/プライバシー/デバイスネットワーク管理/転倒検知対応 |
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
| `world_model.py` | 770 | ゾーン統一状態管理、MQTTトピック解析、9種イベント検知(CO2超過/温度急変/長時間座位/ドア開閉/転倒検知等) |
| `data_classes.py` | 207 | Pydanticモデル5種: EnvironmentData, OccupancyData, DeviceState, Event, ZoneState |
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
- **Fall Detection Response**: 転倒検知イベント→speak(alert)+create_task(urgency=4)の2段階対応

---

## 2. Voice Service (`services/voice/`)

**役割**: VOICEVOX経由の日本語音声合成 + LLMテキスト生成。

| ファイル | 行数 | 役割 |
|---------|------|------|
| `src/main.py` | 466 | FastAPI エンドポイント16種 |
| `src/speech_generator.py` | 384 | VOICEVOX合成パイプライン (speaker_id=47, ナースロボ_タイプT) + 通貨単位名生成 + 受諾/リジェクションテキスト生成 |
| `src/voicevox_client.py` | 105 | VOICEVOX REST APIクライアント (4スピーカーバリアント: normal/cool/happy/whisper) |
| `src/models.py` | 40 | Pydanticリクエスト/レスポンスモデル |
| `src/rejection_stock.py` | 208 | リジェクション音声事前生成 (max 100、アイドル時LLM+VOICEVOX) |
| `src/acceptance_stock.py` | 209 | 受諾音声事前生成 (max 50、アイドル時LLM+VOICEVOX) |
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
| GET | `/api/voice/acceptance/random` | ストックからランダム受諾音声 |
| GET | `/api/voice/acceptance/status` | 受諾ストック状況 |
| POST | `/api/voice/acceptance/clear` | 受諾ストック再生成 |
| GET | `/api/voice/currency-units/status` | 通貨単位ストック状況 + サンプル |
| POST | `/api/voice/currency-units/clear` | 通貨単位ストック再生成 |
| GET | `/audio/{filename}` | 生成済みMP3配信 |
| GET | `/audio/rejections/{filename}` | リジェクション音声配信 |
| GET | `/audio/acceptances/{filename}` | 受諾音声配信 |

---

## 3. Perception Service (`services/perception/`)

**役割**: YOLOv11ベースのコンピュータビジョン。カメラ自動発見、在室検知、活動分析、MTMC人物追跡。

### コアモジュール

| モジュール | ファイル数 | 主要クラス |
|-----------|-----------|-----------|
| `monitors/` | 5 | `MonitorBase`, `OccupancyMonitor`, `WhiteboardMonitor`, `ActivityMonitor`, `TrackingMonitor` |
| `tracking/` | 6 | `CrossCameraTracker`, `ArUcoCalibrator`, `ReIDEmbedder`, `Tracklet`, `MTMCPublisher`, `Homography` |
| `image_sources/` | 5 | `ImageSourceFactory`, `RtspSource`, `HttpStreamSource`, `MqttImageSource`, `CameraInfo` |
| (ルート) | ~7 | `main.py`, `camera_discovery.py`, `pose_estimator.py`, `activity_analyzer.py`, `fall_detector.py`, `yolo_inference.py` |

### 機能

- **カメラ自動発見**: 非同期TCPポートスキャン + URLプローブ + YOLO検証 (192.168.128.0/24)
- **在室モニタ**: YOLO物体検知 → 人数カウント → MQTT publish
- **ホワイトボード**: 変化検知 → キャプチャ
- **活動分析**: 4段ティアードバッファ (最大4時間)、姿勢正規化、長時間座位検知
- **ポーズ推定**: YOLO11s-pose → 17キーポイント
- **MTMC人物追跡**: 複数カメラ間の人物同一性追跡 (ArUcoマーカーによる座標キャリブレーション、ReID特徴量埋め込み、ホモグラフィ変換)
- **転倒検知**: 幾何学的ヒューリスティック (胴体角度/頭部位置/bbox比率/急激変化/足首幅) + 家具コンテキスト判別 (IoU/腰位置ペナルティ)。5秒確認→アラート→120秒クールダウン。`office/{zone}/safety/fall` トピックに publish

---

## 4. Dashboard Service (`services/dashboard/`)

### Backend (FastAPI + SQLAlchemy async + PostgreSQL)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `backend/main.py` | 77 | FastAPIアプリ初期化、CORS、6ルーター登録 |
| `backend/database.py` | 13 | PostgreSQL (asyncpg) 非同期エンジン |
| `backend/models.py` | 88 | SQLAlchemyモデル: Task(27列), VoiceEvent, SystemStats, User |
| `backend/schemas.py` | 118 | Pydantic 2.xスキーマ (TaskCreate/Update/Accept, UserBase, etc.) |
| `backend/sensor_schemas.py` | 62 | センサーデータ用Pydanticスキーマ (LLM Timeline含む) |
| `backend/spatial_config.py` | 114 | 空間設定・フロアプラン読み込み |
| `backend/routers/tasks.py` | 414 | タスクCRUD: 2段階重複検知、受諾/完了/リマインダー/キュー管理、wallet連携 |
| `backend/routers/users.py` | 78 | ユーザーCRUD (list/get/create/update) — AsyncSession実装 |
| `backend/routers/voice_events.py` | 47 | speakツール用エフェメラルイベント記録 (60秒ポーリング) |
| `backend/routers/sensors.py` | 164 | センサーデータAPI (latest/time-series/zones/events/llm-activity/llm-timeline) |
| `backend/routers/spatial.py` | 106 | 空間API (config/live/heatmap) |
| `backend/routers/devices.py` | 141 | デバイス位置管理API (CRUD) |
| `backend/repositories/` | 717 | Repositoryパターン: SensorDataRepository + SpatialDataRepository (ABC + PgSQL実装 + DI) |

### Frontend (React 19 + TypeScript + Vite 7 + Tailwind CSS 4)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `src/App.tsx` | 350 | メインダッシュボード: 3カラムグリッド、TanStack Query (5秒/3秒ポーリング)、ErrorBoundary |
| `src/api.ts` | 188 | API クライアント (authFetch JWT統合、Array.isArray ガード付き) |
| `src/auth/authFetch.ts` | 61 | JWT認証付きfetchラッパー (401自動リフレッシュ+リトライ、失敗時強制ログアウト) |
| `src/hooks/useAnalytics.ts` | 218 | センサー/LLM/デバイス/ヒートマップ用TanStack Queryフック (authFetch統合) |
| `src/pages/AnalyticsPage.tsx` | 1,119 | Analytics: ゾーン概要、デバイス状態監視、時系列チャート、LLM Timeline、占有ヒートマップ、イベントフィード |
| `src/components/ErrorBoundary.tsx` | 49 | React ErrorBoundary (エラー表示+リロードボタン) |
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

## 7.5 Auth Service (`services/auth/`)

**役割**: OAuth認証 (Slack + GitHub) + JWT トークン発行。

| ファイル | 行数 | 役割 |
|---------|------|------|
| `src/main.py` | 24 | FastAPIアプリ、lifespan で auth スキーマ・テーブル自動作成 |
| `src/config.py` | 50 | 環境変数からの設定読み込み |
| `src/database.py` | 14 | SQLAlchemy async engine (他サービスと同パターン) |
| `src/models.py` | 42 | `OAuthAccount`, `RefreshToken` (auth スキーマ) |
| `src/schemas.py` | 65 | Pydantic リクエスト/レスポンスモデル |
| `src/security.py` | 70 | JWT (HS256) 生成/検証、OAuth state トークン |
| `src/user_service.py` | 88 | ユーザー検索・自動作成 (`public.users`) |
| `src/providers/base.py` | 30 | OAuth プロバイダ ABC |
| `src/providers/slack.py` | 65 | Slack OpenID Connect |
| `src/providers/github.py` | 80 | GitHub OAuth |
| `src/routers/oauth.py` | 110 | `GET /{provider}/login`, `GET /{provider}/callback` |
| `src/routers/token.py` | 130 | `POST /token/refresh`, `POST /token/revoke`, `GET /token/me` |

**JWT仕様**: HS256, アクセストークン15分 (`{ sub: user_id, username, display_name, iss: "soms-auth" }`)、リフレッシュトークン30日 (SHA-256ハッシュ、単一使用ローテーション)。`JWT_SECRET` 環境変数を auth/wallet/dashboard 間で共有。

**テスト**: `services/auth/tests/` に97ユニットテスト (conftest + 6テストモジュール)

---

## 7.6 SwitchBot Cloud Bridge (`services/switchbot/`)

**役割**: SwitchBot Cloud API v1.1 デバイスを MQTT 経由で SOMS に統合。ESP32 エッジデバイスと同じテレメトリ形式 (`{"value": X}` per-channel) および MCP JSON-RPC 2.0 プロトコルを使用。

| ファイル | 行数 | 役割 |
|---------|------|------|
| `src/main.py` | 70 | 非同期エントリポイント、コンポーネントオーケストレーション |
| `src/config_loader.py` | 85 | YAML設定 + `${ENV_VAR}` 展開 |
| `src/switchbot_api.py` | 100 | HMAC-SHA256 認証 Cloud API クライアント (10,000リクエスト/日) |
| `src/mqtt_bridge.py` | 75 | MQTT接続、MCPリクエストルーティング |
| `src/device_manager.py` | 90 | ポーリングスケジューラ (センサー: 2分, アクチュエータ: 5分)、ハートビート (60秒) |
| `src/webhook_server.py` | 65 | aiohttp Webhook レシーバ (リアルタイムイベントプッシュ) |
| `src/devices/` | 9ファイル | デバイス実装 (meter, bot, curtain, plug, lock, light, motion_sensor, contact_sensor, ir_device) |

設定: `config/switchbot.yaml`。環境変数: `SWITCHBOT_TOKEN`, `SWITCHBOT_SECRET`。

---

## 8. Infrastructure (`infra/`)

### Docker Compose

| ファイル | サービス数 | 用途 |
|---------|-----------|------|
| `docker-compose.yml` | 14 | 本番構成: mosquitto, brain, postgres, backend, frontend, voicevox, voice-service, wallet, wallet-app, auth, ollama, mock-llm, switchbot, perception |
| `docker-compose.edge-mock.yml` | 3 | 仮想構成: virtual-edge + mock-llm + virtual-camera |

### サービスポート

| サービス | ポート | コンテナ名 |
|---------|--------|-----------|
| Dashboard Frontend (nginx) | 80 | soms-frontend |
| Dashboard Backend API | 8000 | soms-backend |
| Mock LLM | 8001 | soms-mock-llm |
| Voice Service | 8002 | soms-voice |
| Wallet Service | 127.0.0.1:8003 | soms-wallet |
| Wallet App (PWA) | 8004 (HTTPS: 8443) | soms-wallet-app |
| SwitchBot Bridge (Webhook) | 8005 | soms-switchbot |
| Auth Service | 127.0.0.1:8006 | soms-auth |
| PostgreSQL | 127.0.0.1:5432 | soms-postgres |
| VOICEVOX Engine | 50021 | soms-voicevox |
| Ollama (LLM) | 11434 | soms-ollama |
| MQTT Broker | 1883 (TCP) / 9001 (WS) | soms-mqtt |

---

## 9. 直近コミット履歴

```
6e36ef9 feat: add fall detection with furniture-aware discrimination
ff76538 docs: update implementation status for Session W
2f431c1 feat: add device status monitoring and occupancy heatmap to analytics dashboard
fbeee7f docs: update implementation status for Session V
31efec7 feat: add LLM decision timeline chart, error boundary, and authFetch fix
b17362f docs: sync documentation with Auth, SwitchBot, MTMC, and 587-test coverage
3034ad6 feat: add Docker smoke test and wire JWT auth into dashboard frontend
b7b1ed5 feat: implement Phase 0 completion — 6 parallel streams
429a9a8 test: add 47 unit tests for auth-protected endpoints
6793127 test: add 88 unit tests for wallet and dashboard JWT middleware
867cdc4 test: add 97 unit tests for auth service and fix JWT sub claim type
f87a788 feat: add MTMC person tracking with ArUco calibration
3fee40a feat: add OAuth auth service (Slack + GitHub) with JWT-based API protection
d2852a1 feat: add SwitchBot Cloud Bridge service for IoT device integration
```

---

## 10. 既知の問題・改善候補

| 優先度 | 項目 | 詳細 |
|--------|------|------|
| 中 | 24h 安定稼働テスト | Phase 0 完了判定の最終条件 |
| 中 | Production Ollama検証 | Qwen2.5:14b + AMD GPU (ROCm) での実動作テスト |

---

## 11. テストカバレッジ

### ユニットテスト (pytest, サービス不要)

**合計: 711件 / 7サービス / 50テストファイル**

| サービス | テスト数 | テストファイル | テスト対象 |
|---------|---------|---------------|-----------|
| Brain | 167 | `test_queue_manager.py`, `test_sanitizer.py`, `test_sensor_fusion.py`, `test_tool_registry.py`, `test_tool_executor.py`, `test_dashboard_client.py` | タスクスケジューリング、入力検証、センサーフュージョン、ツール定義、ツール実行ルーティング、Dashboard REST クライアント |
| Dashboard | 159 | `test_jwt_auth.py`, `test_auth_endpoints.py`, `test_task_endpoints.py`, `test_sensor_endpoints.py`, `test_device_endpoints.py`, `test_voice_events.py` | JWT認証ミドルウェア、認証保護EP、タスクCRUD、センサーAPI、デバイス位置API、音声イベントAPI |
| Auth | 97 | `test_jwt_middleware.py`, `test_providers.py`, `test_routers_oauth.py`, `test_routers_token.py`, `test_security.py`, `test_user_service.py` | OAuth (Slack/GitHub)、JWT生成/検証、ミドルウェア、ユーザー自動作成 |
| Perception | 86 | `test_aruco_calibrator.py`, `test_reid_embedder.py`, `test_tracklet.py`, `test_fall_detector.py` | ArUcoキャリブレーション、ReID特徴量、トラックレット管理、転倒検知 (胴体角度/家具判別/状態マシン/クールダウン) |
| Voice | 79 | `test_api.py`, `test_acceptance_stock.py`, `test_rejection_stock.py`, `test_currency_unit_stock.py` | FastAPIエンドポイント16種、受諾/リジェクション/通貨単位ストック管理 |
| Wallet | 64 | `test_jwt_auth.py`, `test_auth_endpoints.py` | JWT認証ミドルウェア、金融エンドポイント保護 (P2P送金、ステーク) |
| SwitchBot | 59 | `test_config_loader.py`, `test_device_manager.py`, `test_switchbot_api.py` | YAML設定ロード、ポーリングスケジューラ、Cloud API認証 |

### 実行コマンド

```bash
# 全サービス一括 (conftest衝突回避のためサービス毎に実行)
for d in services/brain/tests services/auth/tests services/voice/tests services/dashboard/backend/tests services/wallet/tests services/switchbot/tests services/perception/tests; do echo "=== $d ===" && .venv/bin/python -m pytest "$d" -v --tb=short; done

# サービス個別
.venv/bin/python -m pytest services/brain/tests/          # Brain: 167件
.venv/bin/python -m pytest services/auth/tests/           # Auth: 97件
.venv/bin/python -m pytest services/voice/tests/          # Voice: 79件
.venv/bin/python -m pytest services/dashboard/backend/tests/  # Dashboard: 159件
.venv/bin/python -m pytest services/wallet/tests/         # Wallet: 64件
.venv/bin/python -m pytest services/switchbot/tests/      # SwitchBot: 59件
.venv/bin/python -m pytest services/perception/tests/     # Perception: 86件
```

### 統合テスト (サービス起動が必要)

```bash
python3 infra/tests/integration/test_docker_smoke.py          # Docker Compose スモークテスト (25テスト)
python3 infra/tests/integration/integration_test_mock.py     # メイン統合テスト (7シナリオ)
python3 infra/tests/integration/test_wallet_integration.py   # Wallet直接テスト
python3 infra/tests/integration/test_sensor_api.py           # センサーデータAPI
python3 infra/tests/e2e/test_wallet_dashboard_e2e.py         # Wallet↔Dashboard E2E
```

---

## 12. セッション履歴

| セッション | 主な成果 | 代表コミット |
|-----------|---------|-------------|
| G | Brain 7層改善 (スレッド安全性, ReAct ガード, Sanitizer 強化) | `091f360` |
| H | ウォレット分離設計, ISSUES 対応 | `246ffc6` |
| I | タスク完了レポート, 並行開発基盤 (WORKER_GUIDE, API_CONTRACTS) | `e07602e` |
| J | 全 CRITICAL/HIGH ISSUES 解消, healthcheck 追加 | `c689908` |
| K | QR リワードフロー, wallet-app デプロイ, MQTT 認証 | `8dabbe2` |
| L | Phase 1.5 出資モデル, Event Store, Brain WalletBridge | `53a6157` |
| M | Wallet↔Dashboard E2E テスト, MQTT auth 修正, nginx DNS修正 | `c4c37cc` |
| N | Wallet App 出資 UI, Tailwind v4 ビルド修正 | `0f5b1f4` |
| O | TanStack Query 移行, pnpm 移行, hadolint | `cfffaf1` |
| P | Sensor Data API + Repository パターン | `bad0cac` |
| Q | Spatial Map Service (フロアプラン可視化 + デバイス配置GUI) | `4101019` |
| R | Federation Phase 1 (全サービスに region_id 追加) | `bdfabfc` |
| S | Device Trust, 3D筐体, 実フロアプラン (DXF), ドキュメント整理 | `a0a3fc0` |
| T | SwitchBot Cloud Bridge, OAuth認証 (Slack+GitHub), HTTPS, MTMC追跡, ユニットテスト 185件 | `6793127` |
| U | ドキュメント整備, テスト拡充 (587件: Brain 167 + Auth 97 + Voice 79 + Dashboard 71 + Wallet 64 + SwitchBot 59 + Perception 50) | `b7b1ed5` |
| V | Docker Smoke Test, Dashboard JWT authFetch統合, LLM Decision Timelineチャート, ErrorBoundary, useAnalytics authFetch修正 | `31efec7` |
| W | デバイス状態監視UI (バッテリー/接続/XP/電力モード), 占有ヒートマップ可視化 (ゾーン選択/期間切替/カラーグリッド) | `2f431c1` |
| X | Dashboard Backend テスト拡充 (+88件→159件: タスクCRUD/センサー/デバイス/音声イベント), authFetch 強制ログアウト | `ff76538` |
| Y | 転倒検知 (FallDetector: 幾何学的姿勢解析+家具コンテキスト判別+状態マシン, ActivityMonitor統合, Brain WorldModel/SystemPrompt対応, 36テスト) | `6e36ef9` |

---

## 13. アーキテクチャ図

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

## 14. 技術スタック

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
