# ADR: Spatial World Model — ゾーン空間情報 + フロントエンド可視化

**Status**: Proposed
**Date**: 2026-02-22
**Context**: WorldModel の空間認識強化 + ダッシュボード可視化

---

## 1. Problem Statement

現在の WorldModel はゾーンを **文字列ID** (例: `"main"`) のみで表現しており、空間的な位置情報を持たない。

| 情報 | 現状 | 不足しているもの |
|------|------|----------------|
| ゾーン | `"main"` 文字列 | 寸法・境界 (x, y, w, h) |
| センサー | `device_id` のみ | 座標 (x, y, z) + カバレッジ半径 |
| カメラ | IP → ゾーン名マップのみ | 座標 + 向き + FOV 角 |
| 占有 | ゾーン単位の人数カウント | ゾーン内ヒートマップ (x, y) |
| タスク | `location` テキスト文字列 | ゾーン内座標ピン |

この制約により以下が困難:
- ダッシュボードでの床面図ベース可視化
- LLM への空間文脈提供 (「北東コーナーのセンサー」など)
- カメラ映像と座標の対応付け
- 複数センサーの物理的近接関係を利用した融合判断

---

## 2. Decision

**YAML ベース設定 + DB オーバーライドのハイブリッド構成** を採用する。

```
config/spaces.yaml          ← ベース定義 (git 管理・変更追跡可能)
        ↓ 起動時ロード
SpatialRepository            ← YAML + DB のマージロジック
        ↑ UI 編集時
DB: spatial_overrides        ← 手動変更分のみ保存 (差分管理)
        ↓
backend/routers/spaces.py   ← GET/PUT /spaces/{zone}
        ↓
frontend: <FloorPlanEditor>  ← SVG ベース床面図 + ドラッグ編集
        ↓
WorldModel.spatial_config    ← 起動時ロード → LLM ツールに空間文脈を提供
```

---

## 3. Rationale

### なぜ YAML ベースか

- **既存パターンとの一貫性**: `services/perception/config/monitors.yaml` と同じ構成
- **バージョン管理**: 空間レイアウトの変更が git 履歴で追跡可能
- **コンテナ外で編集可能**: テキストエディタで素直に編集できる
- **初期状態の再現性**: `docker compose up` で常に同じ初期レイアウトが得られる

### なぜ DB オーバーライドか

- **UI 編集対応**: ダッシュボードからドラッグ操作で位置を微調整できる
- **再起動後も保持**: YAML を書き換えずとも UI 変更が永続化される
- **差分が明確**: YAML = デフォルト、DB = 運用者による調整、と役割が分離

### なぜ SVG ベースか (vs react-konva / deck.gl)

- **依存関係ゼロ**: 追加ライブラリ不要、React のみで実装可能
- **スケーラビリティ**: SVG は解像度非依存、印刷・エクスポートにも対応
- **オフィス室内スケール**: WebGL/3D は今フェーズにはオーバースペック

---

## 4. Architecture

### 4.1 設定スキーマ (`config/spaces.yaml`)

```yaml
version: "1.0"
zones:
  main:
    display_name: "メインオフィス"
    floor: 1
    bounds:
      x: 0
      y: 0
      width: 20    # meters
      height: 15   # meters
    devices:
      env_01:
        device_type: sensor
        position: {x: 5.0, y: 3.0, z: 1.5}
        coverage_radius: 5.0          # meters, optional
      light_01:
        device_type: light
        position: {x: 10.0, y: 7.5, z: 2.5}
        service_area:                 # polygon in zone-local coords, optional
          - [8.0, 6.0]
          - [12.0, 6.0]
          - [12.0, 9.0]
          - [8.0, 9.0]
    cameras:
      camera_node_01:
        position: {x: 0.5, y: 0.5, z: 2.5}
        direction: 45                 # degrees (0 = +X axis, CCW)
        fov: 90                       # degrees
        # coverage_polygon は direction + fov から自動計算
```

### 4.2 データベース

新規テーブル `spatial_overrides` (既存 DB に追加):

```sql
CREATE TABLE spatial_overrides (
    id          SERIAL PRIMARY KEY,
    zone_id     VARCHAR(64) NOT NULL,
    entity_type VARCHAR(32) NOT NULL,  -- 'device' | 'camera' | 'zone'
    entity_id   VARCHAR(64) NOT NULL,
    override    JSONB       NOT NULL,  -- 変更されたフィールドのみ
    updated_at  TIMESTAMP   NOT NULL DEFAULT NOW(),
    UNIQUE (zone_id, entity_type, entity_id)
);
```

マージロジック: YAML ロード後、対応する `spatial_overrides` レコードで上書き (shallow merge)。

### 4.3 API エンドポイント

新ルーター `routers/spaces.py`:

| Method | Path | 説明 |
|--------|------|------|
| GET | `/spaces` | 全ゾーン一覧 (ID + display_name + floor) |
| GET | `/spaces/{zone}` | ゾーン完全情報 (bounds + devices + cameras) |
| PUT | `/spaces/{zone}/device/{device_id}` | デバイス位置の手動更新 |
| PUT | `/spaces/{zone}/camera/{camera_id}` | カメラ位置/FOV の手動更新 |
| PUT | `/spaces/{zone}/bounds` | ゾーン境界の手動更新 |
| DELETE | `/spaces/{zone}/device/{device_id}/override` | DB オーバーライドを削除 (YAML デフォルトに戻す) |

### 4.4 フロントエンドコンポーネント構成

```
src/components/spatial/
  FloorPlanViewer.tsx     ← 読み取り専用: センサー値をオーバーレイ表示
  FloorPlanEditor.tsx     ← 編集モード: ドラッグ&ドロップで位置変更
  ZoneCanvas.tsx          ← SVG ベース描画エンジン (共通)
  DevicePin.tsx           ← センサー/デバイスのピンコンポーネント
  CameraFov.tsx           ← カメラ FOV セクター描画
  SensorOverlay.tsx       ← 現在値のバブルオーバーレイ
  OccupancyHeatmap.tsx    ← 占有ヒートマップ (将来)
```

表示モード切り替え:
- **Viewer モード**: センサー現在値、カメラ状態をリアルタイム表示
- **Editor モード**: デバイスをドラッグして位置調整、変更を `PUT /spaces/...` で送信

### 4.5 WorldModel への組み込み

```python
# data_classes.py への追加
class DeviceSpatialConfig(BaseModel):
    position: tuple[float, float, float] | None = None  # (x, y, z) meters
    coverage_radius: float | None = None
    service_area: list[tuple[float, float]] | None = None

class ZoneSpatialConfig(BaseModel):
    bounds: tuple[float, float, float, float]  # (x, y, width, height)
    devices: dict[str, DeviceSpatialConfig] = {}
    cameras: dict[str, CameraSpatialConfig] = {}

class ZoneState(BaseModel):
    # 既存フィールドはそのまま
    ...
    spatial: ZoneSpatialConfig | None = None  # 追加
```

`get_zone_status` ツールのレスポンスに spatial 情報を含めることで、LLM が「南側のセンサーが高温」などの空間的判断を行えるようになる。

---

## 5. Implementation Phases

### Phase A (読み取り先行)
1. `config/spaces.yaml` 作成 (現在の main ゾーン定義)
2. `SpatialRepository` (YAML 読み込みのみ、DB オーバーライドは後回し)
3. `GET /spaces/{zone}` エンドポイント
4. フロントエンドに `FloorPlanViewer` (読み取り専用、センサー値オーバーレイ)
5. WorldModel に `spatial_config` フィールド追加 (ロードのみ)

### Phase B (手動編集)
1. `spatial_overrides` テーブルのマイグレーション追加
2. `SpatialRepository` に DB マージロジック追加
3. `PUT /spaces/...` エンドポイント群
4. フロントエンドに `FloorPlanEditor` (ドラッグ編集 + 保存)

### Phase C (LLM 活用)
1. `get_zone_status` ツールの spatial 情報出力
2. Brain の system prompt に空間認識コンテキスト追加
3. カメラ座標 ↔ 占有ヒートマップの対応付け (Perception 連携)

---

## 6. Alternatives Considered

### 純粋 YAML のみ
- UI 編集不可のため却下。空間レイアウトの微調整はダッシュボードから行いたい。

### 純粋 DB (YAML なし)
- 初期状態が DB データに依存し、`docker compose up` で再現性が失われる。コードレビューでレイアウト変更を追跡できない。

### GeoJSON 形式
- 屋外地理情報向け標準。室内メートル座標系では不要な複雑さ (CRS、投影など) が生じる。
- 将来的に建物全体の地図を Leaflet/MapLibre で扱う場合は再検討。

### react-konva / deck.gl
- Canvas/WebGL ベース。SVG と比較してオフィス室内スケールでの優位性が薄い。
- react-konva: ドラッグ編集は容易だが、依存追加のコストと見合わない。
- deck.gl: ヒートマップ描画に優れるが、3D/大規模データ向けでオーバースペック。

---

## 7. Open Questions

- **座標系**: ゾーンローカル (各ゾーンの左下が原点) vs 建物グローバル座標。Phase A はゾーンローカルで開始し、Phase C でグローバル座標変換を追加する方針。
- **フロアプラン画像**: YAML で SVG ファイルパスを指定できるようにするか、純粋なプログラマティック描画のみにするか。
- **SensorSwarm Leaf ノード**: `swarm_hub_01.leaf_env_01` 形式のデバイス ID を spaces.yaml でどう扱うか (Hub レベルの位置のみ定義、Leaf は相対オフセットで定義するか)。
