# ADR: Federated Multi-Region Architecture

## Status: Draft

## Context

SOMS は現在、単一ローカルマシン上で動作する。今後複数の拠点（オフィス、ラボ等）にシステムを展開し、**同一通貨圏**として統合する必要がある。

### 要件

1. **ハイブリッド設計** — 各拠点はローカル自律運用可能、1台の中央マシンが最終決定権を持つ
2. **データ集約** — 全拠点のセンサデータ・取引・イベントを中央に集約
3. **通貨統一** — 各拠点で通貨発行可能だが、発行量は中央が把握・制御
4. **XP独立** — ゾーンXPはゾーン内で完結（クロスリージョン累積なし）
5. **主権確保 (51%ルール)** — クロスリージョン取引において、デバイスの所属リージョンが過半数の支配権を保持

---

## 1. Core Concepts

### 1.1 Region (リージョン)

物理的なSOMSインストール単位。1台以上のマシン + Edge デバイス群 + ローカルMQTTブローカー。

```yaml
# config/federation.yaml (各リージョンに配置)
region:
  id: "hq"                     # グローバル一意のリージョンID
  display_name: "本社オフィス"
  sovereign: true               # true = 中央権限マシン (全体で1台のみ)
  hub_url: "https://hq.soms.local"  # このリージョンの外部到達URL
  central_url: "https://hq.soms.local"  # Sovereign のURL (自身がsovereignなら同じ)
  timezone: "Asia/Tokyo"
  mqtt:
    broker: "mosquitto"
    port: 1883
    bridge_to_central: false     # sovereign自身は不要
```

非Sovereignリージョンの例:

```yaml
region:
  id: "lab-a"
  display_name: "研究ラボA"
  sovereign: false
  hub_url: "https://lab-a.soms.local"
  central_url: "https://hq.soms.local"
  timezone: "Asia/Tokyo"
  mqtt:
    broker: "mosquitto"
    port: 1883
    bridge_to_central: true
    bridge_topics:              # 中央に転送するトピック
      - "office/#"
```

### 1.2 Sovereignty Hierarchy

```
┌─────────────────────────────────────────────────┐
│              Sovereign (hq)                     │
│  ・全リージョンのデータを集約                       │
│  ・通貨発行量の最終管理                            │
│  ・トランザクション承認/拒否権                      │
│  ・デミュレッジ実行権（唯一）                       │
│  ・リージョン登録/停止権                           │
│  ・コンフリクト発生時の最終裁定                     │
└─────────┬───────────────────┬───────────────────┘
          │                   │
   ┌──────▼──────┐    ┌──────▼──────┐
   │  Region     │    │  Region     │
   │  (lab-a)    │    │  (branch-b) │
   │             │    │             │
   │ ・ローカル   │    │ ・ローカル   │
   │   通貨発行   │    │   通貨発行   │
   │ ・ローカル   │    │ ・ローカル   │
   │   データ管理 │    │   データ管理 │
   │ ・暫定確定   │    │ ・暫定確定   │
   │   (中央承認  │    │   (中央承認  │
   │    まで)     │    │    まで)     │
   └─────────────┘    └─────────────┘
```

### 1.3 Identity Model

#### User Identity

```
グローバルユーザーID = "{region_id}:{local_name}"
例: "hq:tanaka", "lab-a:suzuki"
```

- 各リージョンはローカルユーザーを自由に作成可能
- JWT トークンに `region_id` + `local_name` を含める
- Sovereign はすべてのユーザーの台帳を保持
- ユーザーが物理的に別リージョンにいても、wallet IDは不変

#### Device Identity

```
グローバルデバイスID = "{region_id}.{device_id}"
例: "hq.env_01", "lab-a.swarm_hub_01.leaf_env_01"
```

- MQTTトピックは変更なし（リージョン内は従来通り `office/{zone}/...`）
- 中央集約時にリージョンプレフィックスが付与される

#### Transaction Identity

```
transaction_id = UUID (変更なし、グローバル一意)
reference_id = "{region_id}:{type}:{local_id}"
例: "hq:task:42", "lab-a:infra:env_01:1708300800"
```

---

## 2. Architecture

### 2.1 System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Sovereign Region (hq)                           │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌─────────────────────┐   │
│  │  Brain   │  │Dashboard │  │  Wallet   │  │  Federation Hub     │   │
│  │  (local) │  │ Backend  │  │  (master) │  │                     │   │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │  ・Region Registry  │   │
│       │              │              │         │  ・Event Ingester   │   │
│  ┌────▼──────────────▼──────────────▼────┐   │  ・Conflict Arbiter │   │
│  │           Local MQTT Broker           │   │  ・Supply Auditor   │   │
│  └───────────────────────────────────────┘   │  ・Data Warehouse   │   │
│       │                                      └──────────┬──────────┘   │
│  ┌────▼────┐                                            │              │
│  │  Edge   │                                            │              │
│  │ Devices │                                            │              │
│  └─────────┘                                            │              │
└─────────────────────────────────────────────────────────┼──────────────┘
                                                          │
                              ┌────────────────────────────┤
                              │                            │
               ┌──────────────▼──────────────┐  ┌─────────▼──────────────┐
               │     Region (lab-a)          │  │   Region (branch-b)    │
               │                              │  │                        │
               │  ┌────────┐  ┌────────────┐ │  │  ┌────────┐           │
               │  │ Brain  │  │  Wallet    │ │  │  │ Brain  │  ...      │
               │  │(local) │  │  (replica) │ │  │  │(local) │           │
               │  └───┬────┘  └─────┬──────┘ │  │  └───┬────┘           │
               │  ┌───▼────────────▼──────┐  │  │  ┌───▼──────────────┐ │
               │  │    Local MQTT Broker   │  │  │  │  Local MQTT      │ │
               │  └───┬───────────────────┘  │  │  └──────────────────┘ │
               │  ┌───▼────┐ ┌──────────┐    │  │                        │
               │  │ Edge   │ │ Region   │────┼──┼───→ Federation Hub     │
               │  │Devices │ │ Agent    │    │  │                        │
               │  └────────┘ └──────────┘    │  └────────────────────────┘
               └──────────────────────────────┘
```

### 2.2 New Components

#### Federation Hub (Sovereign のみ)

Sovereign リージョンに追加されるサービス。全リージョンからのイベントを受信・集約・裁定する。

```
services/federation/
├── src/
│   ├── main.py              # FastAPI + lifespan (event consumer)
│   ├── models.py            # FederationEvent, RegionRecord, GlobalSupply
│   ├── registry.py          # Region 登録・ステータス管理
│   ├── event_ingester.py    # イベント受信・検証・golden ledger 書込
│   ├── conflict_arbiter.py  # コンフリクト検出・解決・補償取引生成
│   ├── supply_auditor.py    # 通貨発行量監視・リージョン別上限管理
│   ├── data_warehouse.py    # センサデータ・イベントの統合ストア
│   └── api/
│       ├── regions.py       # Region CRUD + ステータス
│       ├── sync.py          # Event sync endpoints
│       ├── supply.py        # Global supply dashboard
│       └── override.py      # 管理者オーバーライド操作
├── Dockerfile
└── requirements.txt
```

#### Region Agent (非Sovereign リージョン)

各リージョンに配置されるサイドカーサービス。ローカルイベントを Federation Hub に送信し、中央からの応答を処理する。

```
services/region-agent/
├── src/
│   ├── main.py              # メインループ (sync cycle)
│   ├── models.py            # SyncEvent, SyncAck
│   ├── event_collector.py   # ローカルDB/MQTTからイベント収集
│   ├── sync_client.py       # Federation Hub への HTTP 送信
│   ├── wal.py               # Write-Ahead Log (オフライン時バッファ)
│   ├── ack_processor.py     # 中央からの承認/拒否処理
│   └── config.py            # federation.yaml ローダー
├── Dockerfile
└── requirements.txt
```

### 2.3 Transaction Lifecycle (Provisional → Confirmed)

```
User completes task in lab-a
        │
        ▼
┌──────────────────────────────────┐
│ lab-a Wallet: create transaction │
│ status = "provisional"           │
│ balance updated immediately      │
│ user sees reward instantly       │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ Region Agent: queue sync event   │
│ → WAL に書込み                    │
│ → Federation Hub に POST         │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ Federation Hub (hq):             │
│ 1. 発行上限チェック                │
│ 2. reference_id 重複チェック      │
│ 3. Golden Ledger に書込み         │
│ 4. ACK 返送                      │
│    → "confirmed" or "rejected"   │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ Region Agent: process ACK        │
│ confirmed → status = "confirmed" │
│ rejected  → compensating txn     │
│            (debit + notify user) │
└──────────────────────────────────┘
```

**Sovereign (hq) 自身のトランザクション**: Federation Hub に直接書込み → 即座に "confirmed"。

---

## 3. Federation Sync Protocol

### 3.1 Event Types

```python
class FederationEventType(str, Enum):
    # Wallet events
    TRANSACTION      = "transaction"       # 全取引 (task_reward, p2p, infra)
    WALLET_CREATED   = "wallet_created"    # 新規ウォレット
    DEMURRAGE        = "demurrage"         # デミュレッジ (Sovereign のみ発行)

    # Device events
    DEVICE_REGISTERED = "device_registered"
    DEVICE_HEARTBEAT  = "device_heartbeat"
    XP_GRANTED        = "xp_granted"

    # Stake events
    STAKE_PURCHASED  = "stake_purchased"
    STAKE_RETURNED   = "stake_returned"
    FUNDING_OPENED   = "funding_opened"
    FUNDING_CLOSED   = "funding_closed"

    # Data events (bulk)
    SENSOR_BATCH     = "sensor_batch"      # センサデータバッチ
    EVENT_BATCH      = "event_batch"       # WorldModel イベントバッチ
    LLM_DECISION     = "llm_decision"      # LLM 決定ログ
    SPATIAL_BATCH    = "spatial_batch"      # 空間データバッチ
    HOURLY_AGGREGATE = "hourly_aggregate"  # 時間集計データ
```

### 3.2 Sync Event Envelope

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "region_id": "lab-a",
  "event_type": "transaction",
  "timestamp": "2026-02-19T14:30:00+09:00",
  "sequence": 12345,
  "payload": {
    "transaction_id": "uuid",
    "from_user": "lab-a:tanaka",
    "to_user": "lab-a:suzuki",
    "amount": 1500,
    "transaction_type": "TASK_REWARD",
    "reference_id": "lab-a:task:42"
  }
}
```

### 3.3 Sync API (Federation Hub)

```
POST /federation/sync/events        # バッチイベント送信 (Region Agent → Hub)
GET  /federation/sync/ack/{region}  # 未処理ACK取得 (Region Agent ← Hub)
POST /federation/sync/heartbeat     # リージョン生存通知

POST /federation/regions            # リージョン登録
GET  /federation/regions            # リージョン一覧
PUT  /federation/regions/{id}       # リージョン設定変更 (発行上限等)
DELETE /federation/regions/{id}     # リージョン停止

GET  /federation/supply             # グローバル通貨供給量
GET  /federation/supply/{region}    # リージョン別供給量

POST /federation/override/reject    # 管理者: トランザクション強制拒否
POST /federation/override/freeze    # 管理者: リージョン凍結
```

### 3.4 Sync Tiers (データ種別による同期頻度)

| Tier | データ種別 | 同期頻度 | 同期方式 | 遅延許容 |
|------|-----------|---------|---------|---------|
| **T1: Critical** | ウォレット取引, ステーク売買 | リアルタイム | Event push | < 5s |
| **T2: Important** | デバイス登録/HB, XP付与 | 準リアルタイム | 10s バッチ | < 30s |
| **T3: Telemetry** | センサデータ, WorldModel イベント | バッチ | 60s バッチ | < 5min |
| **T4: Archive** | 時間集計, 空間ヒートマップ, LLM決定ログ | バッチ | 10min バッチ | < 1h |

### 3.5 Offline Mode (WAL)

ネットワーク断絶時、Region Agent は Write-Ahead Log にイベントを蓄積:

```
services/region-agent/data/wal/
├── 00001.jsonl       # WAL セグメント (max 10MB)
├── 00002.jsonl
└── checkpoint.json   # 最後に同期成功した sequence
```

復帰時:
1. checkpoint 以降の全イベントを Federation Hub に再送
2. Hub は `event_id` で冪等処理（重複無視）
3. 拒否されたイベントは compensating transaction で巻戻し

**オフライン中の制約**:
- ローカル取引は "provisional" のまま処理可能
- クロスリージョン取引はキュー保留（相手側に到達不能）
- 通貨発行はローカル上限の範囲内で継続
- デミュレッジは実行されない（Sovereign のみの権限）

---

## 4. Currency & Economy

### 4.1 Currency Issuance Model

```
                    ┌─────────────────────────────────┐
                    │   Global System Wallet (hq:0)   │
                    │   ・グローバル発行量の真の記録     │
                    │   ・リージョン別発行枠の管理       │
                    └────────┬──────────┬──────────────┘
                             │          │
              ┌──────────────▼──┐  ┌────▼──────────────┐
              │ hq Local Wallet │  │ lab-a Local Wallet │
              │ System (hq:0)  │  │ System (lab-a:0)   │
              │ 発行枠: ∞       │  │ 発行枠: 100,000/月  │
              └────────────────┘  └────────────────────┘
```

- **Sovereign (hq)**: 発行枠無制限。Global System Wallet と Local System Wallet は同一
- **非Sovereign**: リージョンごとに月間発行枠を設定
  - 枠内であれば即座にローカル発行 (provisional)
  - 枠超過 → Federation Hub が拒否 → compensating transaction
- **発行枠はSovereignが設定・変更可能**

```python
# regions テーブル (Federation Hub DB)
class Region(Base):
    region_id: str            # "lab-a"
    display_name: str         # "研究ラボA"
    is_sovereign: bool        # False
    issuance_limit: int       # 月間発行上限 (milli-units), 0 = unlimited
    issuance_used: int        # 今月の累計発行量
    issuance_period_start: datetime  # 月初リセット日
    status: str               # "active" / "suspended" / "offline"
    last_sync_at: datetime
    created_at: datetime
```

### 4.2 Demurrage (Central Only)

デミュレッジは **Sovereign のみが実行**:

1. Sovereign の demurrage ループが全リージョンの残高を Golden Ledger から取得
2. 各ウォレットに対してデミュレッジ計算
3. DEMURRAGE イベントを生成 → 各リージョンに配信
4. 各リージョンの Region Agent がローカル残高を減額

これにより二重課税を完全に防止する。

### 4.3 XP Model (Zone-Local)

XPはゾーンに紐づくデバイスに蓄積され、**リージョンをまたがない**:

```
Zone Multiplier 計算:
  multiplier = f(zone内デバイスのXP平均)

hq の office ゾーン:
  devices: [hq.env_01 (XP=500), hq.relay_01 (XP=300)]
  avg_xp = 400 → multiplier = 1.2x

lab-a の lab_main ゾーン:
  devices: [lab-a.env_01 (XP=2000), lab-a.co2_01 (XP=1800)]
  avg_xp = 1900 → multiplier = 1.95x
```

- XP付与イベントは T2 で中央に同期（記録のみ）
- 中央は全リージョンのXP分布を閲覧可能だが、計算には介入しない
- ゾーンのmultiplierはそのゾーンのローカルBrainが計算

### 4.4 Cross-Region Economy: 51% Sovereignty Rule

デバイスステーク（出資）において、デバイスが物理的に存在するリージョンが過半数を保持する。

```python
# devices テーブルに追加
class Device(Base):
    # ... existing fields ...
    home_region: str              # デバイスの所属リージョン
    cross_region_share_cap: float # 外部リージョンに売却可能な最大割合 (default: 0.49)
```

#### ステーク購入フロー

```
lab-a のユーザーが hq のデバイスの株を買いたい:

1. lab-a PWA → lab-a Wallet API → (cross-region detected)
   → Federation Hub に転送

2. Federation Hub:
   a. hq.env_01 の現在のステーク構成を確認
      - hq リージョンユーザー: 60 shares (60%)
      - 外部リージョン合計:    15 shares (15%)
      - 購入希望:              10 shares
      - 外部合計 after: 25/100 = 25% ≤ 49% → OK
   b. ステーク購入取引を実行
      - lab-a:suzuki の wallet から debit
      - hq:device_owner の wallet に credit
      - DeviceStake レコード作成

3. 結果を両リージョンに配信
```

#### 制約チェック

```python
def validate_cross_region_stake(device, buyer_region, shares_requested):
    if buyer_region == device.home_region:
        return True  # ローカル購入は無制限

    current_external = sum(
        s.shares for s in device.stakes
        if get_region(s.user_id) != device.home_region
    )
    max_external = int(device.total_shares * device.cross_region_share_cap)

    if current_external + shares_requested > max_external:
        raise ValueError(
            f"Cross-region cap exceeded: "
            f"{current_external + shares_requested}/{max_external} shares"
        )
    return True
```

#### Funding Pool の 51% ルール

```python
# funding_pools テーブルに追加
class FundingPool(Base):
    # ... existing fields ...
    home_region: str
    cross_region_contribution_cap: float  # default: 0.49
```

- プール出資も同じ 49% 上限
- JPY出資（外部資金）の場合、出資者のリージョン所属で判定
- アクティベーション時のシェア配分でも 51% を home_region が保持

---

## 5. Data Aggregation

### 5.1 Central Data Warehouse Schema

Federation Hub は全リージョンのデータを統合する専用スキーマを持つ:

```sql
CREATE SCHEMA federation;

-- リージョン登録
CREATE TABLE federation.regions (
    region_id       VARCHAR PRIMARY KEY,
    display_name    VARCHAR NOT NULL,
    is_sovereign    BOOLEAN DEFAULT FALSE,
    hub_url         VARCHAR,
    issuance_limit  BIGINT DEFAULT 0,
    issuance_used   BIGINT DEFAULT 0,
    issuance_period_start TIMESTAMPTZ,
    status          VARCHAR DEFAULT 'active',
    last_sync_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Golden Ledger (全リージョンの取引の正本)
CREATE TABLE federation.golden_ledger (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID NOT NULL UNIQUE,       -- 冪等性保証
    region_id       VARCHAR NOT NULL REFERENCES federation.regions,
    transaction_id  UUID NOT NULL,
    wallet_id       VARCHAR NOT NULL,            -- "region:user_id" 形式
    counterparty_id VARCHAR,
    amount          BIGINT NOT NULL,
    entry_type      VARCHAR NOT NULL,            -- DEBIT / CREDIT
    transaction_type VARCHAR NOT NULL,
    reference_id    VARCHAR,
    balance_after   BIGINT,
    status          VARCHAR DEFAULT 'confirmed', -- confirmed / rejected
    local_timestamp TIMESTAMPTZ NOT NULL,        -- リージョンでの発生時刻
    central_timestamp TIMESTAMPTZ DEFAULT NOW(), -- 中央受信時刻
    CONSTRAINT uq_golden_event UNIQUE (event_id)
);
CREATE INDEX ix_golden_region ON federation.golden_ledger(region_id);
CREATE INDEX ix_golden_wallet ON federation.golden_ledger(wallet_id);
CREATE INDEX ix_golden_txn ON federation.golden_ledger(transaction_id);
CREATE INDEX ix_golden_ref ON federation.golden_ledger(reference_id);

-- グローバル供給統計
CREATE TABLE federation.global_supply (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    total_issued    BIGINT DEFAULT 0,
    total_burned    BIGINT DEFAULT 0,
    circulating     BIGINT DEFAULT 0,
    last_updated    TIMESTAMPTZ DEFAULT NOW()
);

-- リージョン別供給統計
CREATE TABLE federation.region_supply (
    region_id       VARCHAR PRIMARY KEY REFERENCES federation.regions,
    total_issued    BIGINT DEFAULT 0,
    total_burned    BIGINT DEFAULT 0,
    circulating     BIGINT DEFAULT 0,
    last_synced     TIMESTAMPTZ
);

-- センサデータ集約 (T3: 60s バッチ)
CREATE TABLE federation.sensor_data (
    id              BIGSERIAL PRIMARY KEY,
    region_id       VARCHAR NOT NULL,
    zone            VARCHAR NOT NULL,
    channel         VARCHAR NOT NULL,
    value           DOUBLE PRECISION,
    source_device   VARCHAR,                     -- "region.device_id"
    timestamp       TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_sensor_region_zone ON federation.sensor_data(region_id, zone, timestamp);

-- イベントログ集約 (T3: 60s バッチ)
CREATE TABLE federation.events (
    id              BIGSERIAL PRIMARY KEY,
    region_id       VARCHAR NOT NULL,
    zone            VARCHAR NOT NULL,
    event_type      VARCHAR NOT NULL,
    source_device   VARCHAR,
    data            JSONB,
    timestamp       TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_events_region ON federation.events(region_id, timestamp);

-- 時間集計集約 (T4: 10min バッチ)
CREATE TABLE federation.hourly_aggregates (
    id              BIGSERIAL PRIMARY KEY,
    region_id       VARCHAR NOT NULL,
    period_start    TIMESTAMPTZ NOT NULL,
    zones           JSONB NOT NULL,
    tasks_created   INTEGER DEFAULT 0,
    llm_cycles      INTEGER DEFAULT 0,
    CONSTRAINT uq_hourly_region_period UNIQUE (region_id, period_start)
);

-- LLM 決定ログ (T4: 10min バッチ)
CREATE TABLE federation.llm_decisions (
    id              BIGSERIAL PRIMARY KEY,
    region_id       VARCHAR NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    cycle_duration  FLOAT,
    iterations      INTEGER,
    tool_calls      JSONB,
    trigger_events  JSONB,
    world_state     JSONB
);

-- デバイス台帳 (全リージョン)
CREATE TABLE federation.devices (
    global_device_id VARCHAR PRIMARY KEY,        -- "region.device_id"
    region_id       VARCHAR NOT NULL,
    device_type     VARCHAR,
    owner_id        VARCHAR,                     -- "region:user_id"
    xp              BIGINT DEFAULT 0,
    total_shares    BIGINT DEFAULT 100,
    cross_region_share_cap FLOAT DEFAULT 0.49,
    last_heartbeat  TIMESTAMPTZ,
    status          VARCHAR DEFAULT 'active'
);

-- Sync 進捗管理
CREATE TABLE federation.sync_cursors (
    region_id       VARCHAR PRIMARY KEY REFERENCES federation.regions,
    last_event_seq  BIGINT DEFAULT 0,            -- 最後に処理したシーケンス
    last_sync_at    TIMESTAMPTZ
);
```

### 5.2 Data Retention (Central)

| データ種別 | ローカル保持 | 中央保持 |
|-----------|------------|---------|
| Raw sensor readings | 730日 | 2年 (→ 集計後削除可) |
| Hourly aggregates | 無期限 | 無期限 |
| WorldModel events | 730日 | 2年 |
| Spatial snapshots | 90日 | 180日 |
| LLM decisions | 730日 | 無期限 |
| Golden Ledger | — | 無期限 (監査要件) |

### 5.3 Central Dashboard Queries

Federation Hub は統合ダッシュボード用 API を提供:

```
GET /federation/dashboard/overview
  → 全リージョンのサマリ (ゾーン数, デバイス数, 在室人数, 供給量)

GET /federation/dashboard/sensors?region=&zone=&channel=
  → クロスリージョンのセンサ時系列

GET /federation/dashboard/supply/history
  → 通貨供給量の時系列推移 (リージョン別)

GET /federation/dashboard/economy
  → クロスリージョン取引量, ステーク分布, デバイスXP分布
```

---

## 6. MQTT Federation

### 6.1 Mosquitto Bridge Configuration

各リージョンの MQTT ブローカーを Sovereign にブリッジ:

```conf
# infra/mosquitto/mosquitto.conf (非Sovereign リージョン用)

# 既存設定
persistence true
persistence_location /mosquitto/data/
listener 1883
password_file /mosquitto/config/passwd

# Bridge to Sovereign
connection bridge-to-hq
address hq.soms.local:1883
remote_username soms_bridge_lab-a
remote_password <bridge_password>
topic office/# out 1 "" lab-a/
# ローカル office/zone/... → Sovereign の lab-a/office/zone/...
# QoS 1 (at least once delivery)

notifications true
notification_topic bridge/lab-a/status
```

Sovereign 側では:

```
lab-a/office/{zone}/{device_type}/{device_id}/{channel}
branch-b/office/{zone}/{device_type}/{device_id}/{channel}
office/{zone}/...    # 自身のローカルトピック
```

これにより、Sovereign の Brain は全リージョンのセンサデータを受信可能。

### 6.2 Topic Namespace

```
# Sovereign が受信するトピック構造
{region_id}/office/{zone}/{device_type}/{device_id}/{channel}

# 例
hq/office/meeting_room/sensor/env_01/temperature       # ← 不要 (自身は office/... のまま)
lab-a/office/lab_main/sensor/env_01/temperature
branch-b/office/entrance/sensor/pir_01/motion

# Federation 専用トピック
federation/sync/{region_id}        # Region Agent → Hub 同期
federation/ack/{region_id}         # Hub → Region Agent 応答
federation/broadcast               # Hub → 全リージョン一斉通知
```

---

## 7. Schema Changes (Existing Services)

### 7.1 Wallet Service (`services/wallet/src/models.py`)

```python
# 追加フィールド

class Wallet(Base):
    # ... existing ...
    region_id: str = Column(String, nullable=False, default="local")
    global_user_id: str = Column(String, nullable=True)  # "region:local_id"

class LedgerEntry(Base):
    # ... existing ...
    region_id: str = Column(String, nullable=False, default="local")
    sync_status: str = Column(String, default="pending")
    # "pending" → "synced" → "confirmed" / "rejected"
    central_ack_at: datetime = Column(DateTime(timezone=True), nullable=True)

class Device(Base):
    # ... existing ...
    home_region: str = Column(String, nullable=False, default="local")
    cross_region_share_cap: float = Column(Float, default=0.49)

class FundingPool(Base):
    # ... existing ...
    home_region: str = Column(String, nullable=False, default="local")
    cross_region_contribution_cap: float = Column(Float, default=0.49)
```

### 7.2 Dashboard Backend

```python
# Task model に region 追加
class Task(Base):
    # ... existing ...
    region_id: str = Column(String, nullable=False, default="local")

# User model に global identity
class User(Base):
    # ... existing ...
    region_id: str = Column(String, nullable=False, default="local")
    global_user_id: str = Column(String, nullable=True)
```

### 7.3 Brain Service

```python
# config/federation.yaml を読み込み
# WorldModel の zone state に region_id を付与
# EventWriter の出力に region_id を含める
```

### 7.4 config/federation.yaml

```yaml
# 新規ファイル: 各リージョンに配置
region:
  id: "hq"
  display_name: "本社オフィス"
  sovereign: true
  hub_url: "https://hq.soms.local"
  central_url: "https://hq.soms.local"

federation:
  sync_interval_t1: 1          # Critical events: 1s
  sync_interval_t2: 10         # Important events: 10s
  sync_interval_t3: 60         # Telemetry: 60s
  sync_interval_t4: 600        # Archive: 10min
  wal_dir: "./data/wal"
  wal_max_segment_mb: 10
  offline_max_hours: 72        # WAL 最大蓄積時間

auth:
  jwt_secret: "${FEDERATION_JWT_SECRET}"
  token_expiry: 3600

cross_region:
  default_share_cap: 0.49      # 51% ルールのデフォルト
  min_home_share: 0.51         # ホームリージョン最低保持率
```

---

## 8. Auth Layer

### 8.1 JWT Token Structure

```json
{
  "sub": "hq:tanaka",
  "region_id": "hq",
  "local_user_id": 5,
  "global_user_id": "hq:tanaka",
  "roles": ["user"],
  "iat": 1708300800,
  "exp": 1708304400
}
```

### 8.2 Auth Flow

```
1. ユーザーが Wallet PWA にアクセス
2. リージョンのローカル Auth エンドポイントで認証
   POST /auth/login { "username": "tanaka", "password": "..." }
   → JWT 発行 (region_id + local_user_id 含む)
3. 以降すべての API リクエストに Authorization: Bearer <jwt> を付与
4. Wallet Service は JWT から region_id + user_id を抽出
5. クロスリージョン API 呼出時は同じ JWT を Federation Hub に転送
   Hub は JWT の region_id を検証して信頼
```

### 8.3 Migration from Current (No Auth)

Phase 1 では既存の `localStorage user_id` 方式を維持しつつ、`region_id` を設定ファイルから注入:

```typescript
// wallet-app/src/hooks/useUserId.ts (Phase 1)
const REGION_ID = import.meta.env.VITE_REGION_ID || "local";

function getGlobalUserId(localId: number): string {
  return `${REGION_ID}:${localId}`;
}
```

Phase 2 で JWT 認証を導入。

---

## 9. Migration Path

### Phase 1: Region Identity (基盤整備)

**変更**: region_id をすべてのモデルに追加。デフォルト `"local"` で後方互換。

```
1. config/federation.yaml 作成 (region.id = "local", sovereign = true)
2. Wallet models に region_id カラム追加 (default="local")
3. Dashboard models に region_id カラム追加 (default="local")
4. reference_id 生成を "{region}:{type}:{id}" 形式に変更
5. device_id にリージョンプレフィックスは「まだ付けない」
   (ローカル運用は変わらない)
```

**影響**: 既存の単一インスタンス運用に変更なし。

### Phase 2: Federation Hub (中央構築)

**変更**: Sovereign リージョンに Federation Hub サービスを追加。

```
1. services/federation/ 作成
2. federation スキーマの DB マイグレーション
3. Region Registry API
4. Golden Ledger (初期は hq のローカル ledger をそのまま使用)
5. Supply Auditor (ローカル supply_stats の読み取り)
6. 中央ダッシュボード API (基本)
```

**影響**: hq は Federation Hub を持つが、他リージョンはまだ存在しない。

### Phase 3: Region Agent + First Satellite (最初の分散)

**変更**: 2番目のリージョンを追加。

```
1. services/region-agent/ 作成
2. lab-a 用の federation.yaml 作成
3. WAL (Write-Ahead Log) 実装
4. Sync Protocol 実装 (T1, T2 のみ先行)
5. lab-a の Wallet Service に sync_status カラム追加
6. compensating transaction ロジック
7. MQTT Bridge 設定
```

### Phase 4: Cross-Region Economy (経済統合)

**変更**: クロスリージョンのステーク・送金を有効化。

```
1. 51% ルールのバリデーション実装
2. クロスリージョン P2P 送金フロー
3. クロスリージョン ステーク購入フロー
4. Federation Hub のコンフリクト解決ロジック
```

### Phase 5: Full Data Aggregation + Auth (完全統合)

```
1. T3/T4 データ同期の実装
2. JWT 認証の導入
3. 中央ダッシュボードの全機能
4. デミュレッジの中央一元化
```

---

## 10. Decision Log

| 決定事項 | 選択 | 理由 |
|---------|------|------|
| 通貨供給の正本 | Golden Ledger (中央) | 複数DBに分散すると供給量が不整合になるため |
| ローカル取引の即時性 | Provisional → Confirmed 2段階 | UXを犠牲にせず一貫性を確保 |
| デミュレッジ実行権 | Sovereign のみ | 二重課税防止 |
| XP スコープ | ゾーン内完結 | ゾーンのデバイス貢献を正確に反映するため |
| クロスリージョン上限 | 49% (設定可能) | 物理デバイスの所在地リージョンの主権を確保 |
| 同期プロトコル | HTTP REST (非MQTT) | WAL + リトライに適した request-response 形式 |
| オフライン戦略 | WAL + 復帰時再同期 | ネットワーク不安定な環境でもローカル運用可能 |
| ID 形式 | `region:local_id` (文字列) | 既存の Integer ID との後方互換を維持しつつグローバル一意性確保 |
| Auth 導入時期 | Phase 5 (最後) | ローカル運用の手軽さを優先。分散化が実際に必要になるまで延期 |

---

## Appendix: Data Volume Estimates

### Per-Region Per-Day

| データ | レコード数 | サイズ見積 |
|--------|-----------|----------|
| Sensor readings (raw) | ~8,640/zone × 12 zones | ~1.2 MB |
| WorldModel events | ~600 | ~60 KB |
| LLM decisions | ~2,880 (30s cycle) | ~1.4 MB |
| Spatial snapshots | ~8,640/zone | ~2.4 MB |
| Hourly aggregates | 24 | ~6 KB |
| Wallet transactions | ~50-200 | ~20 KB |
| **Total raw** | | **~5 MB/day** |
| **Total (10 regions)** | | **~50 MB/day** |

中央集約において帯域・ストレージともに十分に実用的な範囲。
