> ⚠️ **v2 B2B note**: this README predates the v2 fork and may reference the v1 credit economy. See [`/docs/architecture/v2-b2b-migration.md`](../../docs/architecture/v2-b2b-migration.md) for the current architecture. v1 preserved at `legacy/v1-with_wallet`.

# Dashboard Service

SOMS のヒューマンインターフェース。タスク管理・センサー可視化・空間マップ・音声イベント閲覧を提供する。

## 構成

```
services/dashboard/
├── backend/      FastAPI バックエンド API (ポート 8000)
└── frontend/     React フロントエンド SPA (nginx ポート 80 経由)
```

## Backend

### 技術スタック

- Python 3.11, FastAPI, SQLAlchemy (async), asyncpg (PostgreSQL) / aiosqlite (fallback)
- Pydantic v2, loguru

### API エンドポイント全覧

Swagger UI: `http://localhost:8000/docs`

#### タスク (`/tasks`)

| Method | Path | 説明 |
|--------|------|------|
| GET | `/tasks/` | アクティブタスク一覧 (期限切れ除く) |
| POST | `/tasks/` | タスク作成 (重複検出 Stage 1&2) |
| PUT | `/tasks/{id}/accept` | タスク受諾・担当者割当 |
| PUT | `/tasks/{id}/complete` | タスク完了・バウンティ支払い |
| PUT | `/tasks/{id}/reminded` | リマインド時刻更新 |
| GET | `/tasks/queue` | キュー済みタスク一覧 |
| PUT | `/tasks/{id}/dispatch` | キュータスクをディスパッチ |
| GET | `/tasks/stats` | タスク統計 (件数・XP・完了数) |

タスク重複検出:
- Stage 1: title + location 完全一致
- Stage 2: zone + task_type 一致

#### センサーデータ (`/sensors`) — 読み取り専用

| Method | Path | 説明 | パラメータ |
|--------|------|------|----------|
| GET | `/sensors/latest` | ゾーン×チャネル最新値 | `?zone=` |
| GET | `/sensors/time-series` | 時系列データ (グラフ用) | `?zone=&channel=&window=1h&start=&end=&limit=168` |
| GET | `/sensors/zones` | 全ゾーン概況スナップショット | — |
| GET | `/sensors/events` | WorldModel イベントフィード | `?zone=&limit=50` |
| GET | `/sensors/llm-activity` | LLM 意思決定サマリー | `?hours=24` |

#### 空間情報 — 3層モデル

**統合 API (`/spaces`)**

| Method | Path | 説明 |
|--------|------|------|
| GET | `/spaces` | Zone 一覧 (Layer1 YAML) |
| GET | `/spaces/{zone}` | Zone 詳細 (Layer1+2 マージ) |
| PUT | `/spaces/{zone}/devices/{id}` | デバイス位置更新 (Layer2 DB) |
| PUT | `/spaces/{zone}/cameras/{id}` | カメラ位置・FOV 更新 (Layer2 DB) |
| GET | `/spaces/{zone}/live` | ライブ検出 (Layer3) |
| GET | `/spaces/{zone}/heatmap` | ヒートマップ `?period=hour\|day\|week` |
| DELETE | `/spaces/{zone}/devices/{id}/override` | DB オーバーライド削除 |
| DELETE | `/spaces/{zone}/cameras/{id}/override` | 同上 (カメラ) |

後方互換: `/sensors/spatial/*` と `/devices/positions/*` も維持。
詳細: `docs/architecture/adr-spatial-world-model.md`

### データモデル

```
Task (27 columns)
  id, title, description, location, zone
  bounty_gold, bounty_xp, urgency (0-4)
  is_completed, is_queued
  created_at, expires_at, completed_at, dispatched_at, accepted_at, last_reminded_at
  task_type (JSON文字列配列), min_people_required, estimated_duration
  announcement_audio_url, announcement_text
  completion_audio_url, completion_text
  report_status, completion_note
  assigned_to, region_id

VoiceEvent: id, message, audio_url, zone, tone, created_at
DevicePosition: device_id, zone, x, y, device_type, channels
CameraPosition: camera_id, zone, x, y, z, fov_deg, orientation_deg
User: id, username, display_name, is_active, region_id, global_user_id
SystemStats: total_xp, tasks_completed, tasks_created
```

### Repository パターン

```
SensorDataRepository (ABC)
  └── PgSensorRepository  → events.* スキーマを直接クエリ

SpatialDataRepository (ABC)
  └── PgSpatialRepository → YAML + DB マージ + events.spatial_* 参照

DInjection: repositories/deps.py (FastAPI Depends)
```

将来の InfluxDB 移行は Repository 実装を差し替えるだけで対応可能。
詳細: `docs/architecture/adr-sensor-api-repository-pattern.md`

### 設定

| 環境変数 | デフォルト | 説明 |
|---------|-----------|------|
| `DATABASE_URL` | sqlite+aiosqlite (fallback) | PostgreSQL 接続 URL |
| `WALLET_SERVICE_URL` | `http://wallet:8000` | Wallet API URL |
| `MQTT_BROKER` / `MQTT_PORT` | `mosquitto` / `1883` | タスク完了報告用 MQTT |
| `MQTT_USER` / `MQTT_PASS` | `soms` / `soms_dev_mqtt` | MQTT 認証 |

### 起動・ログ確認

```bash
docker logs -f soms-backend
# API ドキュメント
open http://localhost:8000/docs
```

---

## Frontend

### 技術スタック

- React 19, TypeScript, Vite 7
- Tailwind CSS 4, Framer Motion, Lucide icons
- TanStack Query (サーバー状態管理)
- pnpm

### ページ構成

| ページ | パス | 説明 |
|--------|------|------|
| タスク一覧 | `/` | ダッシュボードメイン |
| アナリティクス | `/analytics` | センサーデータ・ヒートマップ・LLM 活動 |
| 床面図 | `/floor-plan` | 空間マップ・デバイス配置 |
| ウォレット | (外部) | Wallet PWA (ポート 8004) |

### コンポーネント構成

```
src/
├── components/
│   ├── FloorPlan/
│   │   ├── FloorPlanView.tsx    ビューアー + エディター (editMode トグル)
│   │   ├── ZoneLayer.tsx        SVG ポリゴン描画
│   │   ├── DeviceLayer.tsx      デバイスピン + ドラッグ + センサー値
│   │   ├── CameraFov.tsx        カメラ FOV 扇形 (fov_deg + orientation_deg)
│   │   ├── HeatmapLayer.tsx     占有ヒートマップグリッド
│   │   ├── PersonLayer.tsx      ライブ人物検出ドット
│   │   ├── FloorPlanControls.tsx レイヤートグル
│   │   └── DeviceDetailPanel.tsx 選択デバイス詳細
│   └── TaskCard.tsx
├── pages/
│   ├── AnalyticsPage.tsx        センサー時系列・デバイス状態・ヒートマップ
│   └── FloorPlanPage.tsx        床面図ページ
├── hooks/
│   └── useAnalytics.ts          TanStack Query フック集
├── types/
│   └── spatial.ts               空間型定義
└── api.ts                       API クライアント関数
```

### 床面図レイヤー

| レイヤー | 内容 | デフォルト |
|---------|------|----------|
| `zones` | ゾーンポリゴン | ON |
| `devices` | センサー/デバイスピン | ON |
| `cameras` | カメラ FOV 扇形 | OFF |
| `heatmap` | 占有ヒートマップ | OFF |
| `persons` | ライブ人物ドット | ON |
| `objects` | ライブ物体ドット | OFF |

編集モード (`editMode = true`) ではデバイスをドラッグで移動可能。変更は `PUT /spaces/{zone}/devices/{id}` で保存。

### ローカル開発

```bash
cd services/dashboard/frontend
pnpm install
pnpm run dev    # Vite dev server (http://localhost:5173)
pnpm run build  # tsc -b && vite build
pnpm run lint   # ESLint
```

nginx のプロキシ設定: `services/dashboard/frontend/nginx.conf`
