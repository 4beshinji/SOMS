# ADR: Spatial World Model — ゾーン空間情報 + フロントエンド可視化

**Status**: Accepted
**Date**: 2026-02-22 (revised 2026-02-23)
**Context**: WorldModel の空間認識強化 + ダッシュボード可視化

---

## 1. Problem Statement

WorldModel はゾーンを**文字列ID**のみで表現しており、空間的な位置情報を持たなかった。
これによりダッシュボードでの床面図可視化・LLM への空間文脈提供・カメラ映像と座標の対応付けが困難だった。

---

## 2. Decision: 3層空間モデル

空間データには**ライフサイクルが根本的に異なる3層**が存在する。
各層を明確に分離し、それぞれに適したストレージと更新経路を持つ。

```
Layer 1 — Topology    変化頻度: 月〜年単位
  ゾーンポリゴン、建物寸法、ArUco キャリブレーション座標
  ストレージ: config/spatial.yaml (git 管理)
  更新方法:  テキストエディタ + git commit

Layer 2 — Placement   変化頻度: 日〜週単位
  デバイス位置 (x, y, z)、カメラ位置・FOV
  ストレージ: device_positions / camera_positions テーブル
  更新方法:  ダッシュボード UI (ドラッグ&ドロップ)

Layer 3 — Observations 変化頻度: 秒〜分単位
  ライブ検出 (人物・物体座標)、ヒートマップ集計
  ストレージ: events.spatial_snapshots / events.spatial_heatmap_hourly
  更新方法:  Perception サービスが MQTT 経由で自動書き込み
```

---

## 3. Architecture

### 3.1 API 構造 (`/spaces`)

```
GET  /spaces                              → Zone 一覧 (Layer 1)
GET  /spaces/{zone}                       → Zone 詳細 (Layer 1 + 2 マージ済み)
PUT  /spaces/{zone}/devices/{device_id}   → デバイス位置更新 (Layer 2)
PUT  /spaces/{zone}/cameras/{camera_id}   → カメラ位置更新 (Layer 2)
GET  /spaces/{zone}/live                  → ライブ検出 (Layer 3)
GET  /spaces/{zone}/heatmap?period=hour   → ヒートマップ (Layer 3)
DELETE /spaces/{zone}/devices/{id}/override  → DB オーバーライド削除 (YAML に戻す)
DELETE /spaces/{zone}/cameras/{id}/override  → 同上 (カメラ)
```

**後方互換性**: 既存の `/sensors/spatial/*` と `/devices/positions/*` は維持。

### 3.2 データベーススキーマ

```sql
-- Layer 2: デバイス位置 (既存)
CREATE TABLE device_positions (
    id          SERIAL PRIMARY KEY,
    device_id   VARCHAR UNIQUE NOT NULL,
    zone        VARCHAR NOT NULL,
    x FLOAT, y FLOAT,
    device_type VARCHAR DEFAULT 'sensor',
    channels    VARCHAR DEFAULT '[]',
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP
);

-- Layer 2: カメラ位置 (追加)
CREATE TABLE camera_positions (
    id              SERIAL PRIMARY KEY,
    camera_id       VARCHAR UNIQUE NOT NULL,
    zone            VARCHAR NOT NULL,
    x FLOAT, y FLOAT, z FLOAT,
    fov_deg         FLOAT,
    orientation_deg FLOAT,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP
);
-- DB レコードがなければ YAML のカメラ設定がそのまま使われる (オーバーライドのみ保存)
```

### 3.3 Brain の空間設定取得フロー

```
Brain.run() 起動
    ↓
DashboardClient.get_spatial_config()
    → GET /sensors/spatial/config (Backend が Layer 1+2 をマージして返す)
    ↓ 失敗時 (Backend 未起動など)
load_spatial_config("config/spatial.yaml")  (YAML フォールバック)
    ↓
WorldModel.apply_spatial_config(config)
    → ZoneState.metadata に polygon / area_m2 / adjacent_zones を設定
    → ZoneState.spatial.heatmap_counts グリッドを初期化
```

**重複コードの解消**: Brain が YAML を直接読まず Backend 経由で取得することで、
`services/brain/src/spatial_config.py` と `services/dashboard/backend/spatial_config.py`
の重複ローダーを段階的に統合する経路が開かれた。

### 3.4 リポジトリパターン (Backend)

```
routers/spaces.py  (統合 API エンドポイント)
routers/spatial.py (後方互換: /sensors/spatial/*)
routers/devices.py (後方互換: /devices/positions/*)
        │
        ▼
SpatialDataRepository (ABC)
        │
        └── PgSpatialRepository
              ├── get_spatial_config()  → YAML + device_positions + camera_positions マージ
              ├── get_live_spatial()    → events.spatial_snapshots 参照
              └── get_heatmap()         → events.spatial_heatmap_hourly 参照
```

### 3.5 フロントエンドコンポーネント構成

```
src/components/FloorPlan/
  FloorPlanView.tsx       ← Viewer + Editor (editMode トグル)
  ZoneLayer.tsx           ← SVG ポリゴン描画 + 重心ラベル
  DeviceLayer.tsx         ← デバイスピン + ドラッグ + センサー値バブル
  CameraFov.tsx           ← カメラ FOV 扇形 (新規)
  HeatmapLayer.tsx        ← 占有ヒートマップグリッド
  PersonLayer.tsx         ← ライブ人物検出ドット
  FloorPlanControls.tsx   ← レイヤートグル
  DeviceDetailPanel.tsx   ← 選択デバイスの詳細パネル
```

レイヤー種別: `'zones' | 'devices' | 'cameras' | 'heatmap' | 'persons' | 'objects'`

### 3.6 LLM への空間文脈提供

`get_zone_status` ツールのレスポンスに追加済み:
- `面積: {area_m2}㎡`
- `隣接ゾーン: {adjacent_zones}`
- `検出位置: (x.xm, y.ym), ...` (floor_position_m を持つ検出のみ)

---

## 4. Rationale

### なぜポリゴン形状か (矩形ではなく)
L字型・変則形状の室内レイアウトに対応するため。矩形 `(x,y,w,h)` では実際のゾーン形状を表現できない。

### なぜ具体テーブル2本か (汎用 `spatial_overrides` ではなく)
`device_positions` と `camera_positions` は編集フィールドが異なる。
型安全・クエリ明確さ・マイグレーション容易さの点で具体テーブルが優れる。
汎用 JSONB テーブルは3つ目のエンティティ型が必要になった時点で再検討。

### なぜ SVG か (react-konva / deck.gl ではなく)
追加依存なし。室内メートル座標スケールでは WebGL の優位性なし。
SVG は解像度非依存で印刷・エクスポートにも対応。

### なぜ REST フォールバックを持つか
Brain と Backend は同時起動するが起動順序は不定。
YAML フォールバックにより Backend が遅延起動した場合も Brain が正常起動する。

---

## 5. Implementation Status

| 機能 | ステータス | 実装場所 |
|------|-----------|---------|
| `config/spatial.yaml` (ポリゴン定義) | ✅ | `config/spatial.yaml` |
| SpatialDataRepository + PgSpatialRepository | ✅ | `repositories/` |
| `/sensors/spatial/config,live,heatmap` | ✅ | `routers/spatial.py` |
| `/devices/positions/` CRUD | ✅ | `routers/devices.py` |
| `camera_positions` テーブル | ✅ | `models.py` |
| `PUT /devices/cameras/{id}` | ✅ | `routers/devices.py` |
| `/spaces` 統合ルーター | ✅ | `routers/spaces.py` |
| Brain → REST 経由 spatial 取得 | ✅ | `dashboard_client.py` + `main.py` |
| `CameraFov.tsx` FOV 可視化 | ✅ | `components/FloorPlan/CameraFov.tsx` |
| `get_zone_status` 空間文脈 | ✅ | `tool_executor.py` |
| フロアプラン viewer + editor | ✅ | `components/FloorPlan/` |
| ヒートマップ可視化 | ✅ | `HeatmapLayer.tsx` + `AnalyticsPage.tsx` |
| ArUco キャリブレーション | ✅ | `config/spatial.yaml` |
| ゾーン境界の UI 編集 | ❌ | 多角形エディタは複雑 → Phase 2 以降 |

---

## 6. Open Questions

- **`spatial_config.py` の重複**: Brain が常に Backend 経由で取得するようになれば
  `services/brain/src/spatial_config.py` を削除できる。現状は YAML フォールバック用に維持。
- **ゾーン境界の手動編集**: テキストエディタで YAML を編集 → コンテナ再起動が当面の運用方法。
- **SensorSwarm Leaf ノード**: `swarm_hub_01.leaf_env_01` 形式の device_id を
  `device_positions` にどう持つか未決定。Hub レベルの位置のみで十分か要検討。
