# 在庫管理 拡張計画 — キャリブレーション・物品登録・マルチアイテム

**作成日**: 2026-03-13
**前提**: Step 1-7 (重量ベース基盤) 実装済み。本ドキュメントは残り3つの課題に対する実装計画。

---

## 現状の問題点

| # | 課題 | 現状 | 影響 |
|---|------|------|------|
| A | キャリブレーション | HX711 ドライバに `tare()`/`set_scale()` はあるが、`scale` 値は `config.json` に静的記述。校正手順なし | ロードセル個体差で重量がずれる。現場で校正できない |
| B | 物品重量登録 | `config/inventory.yaml` に `unit_weight_g` を手書き。変更にはYAML編集+再起動が必要 | 新しい物品を追加するたびにデプロイが必要。運用コストが高い |
| C | 1センサ複数品目 | キー `device_id:channel` が1対1マッピング。棚に複数品目を載せると合計重量しか取れない | 現実の棚は複数品目が混在する。品目別の数量が出せない |

---

## A. 重量センサ キャリブレーション

### A.1 概要

ロードセル+HX711 の出力は ADC 生値であり、グラムに変換するには `scale` (生値/g) と `offset` (ゼロ点) の2パラメータが必要。これをリモートから校正可能にする。

### A.2 校正フロー

```
ユーザー: 棚を空にする
    ↓
Brain LLM → calibrate_shelf(device_id, step="tare")
    ↓
ToolExecutor → MCP call_tool → shelf_01/tare
    ↓
ESP32: HX711.tare(readings=20) → offset 記録
    ↓
ユーザー: 既知重量の物を載せる (例: 1kg の重り)
    ↓
Brain LLM → calibrate_shelf(device_id, step="set_known_weight", weight_g=1000)
    ↓
ToolExecutor → MCP call_tool → shelf_01/calibrate {"known_weight_g": 1000}
    ↓
ESP32: raw = HX711._read_raw() → scale = (raw - offset) / 1000 → EEPROM 保存
    ↓
応答: {"status": "ok", "scale": 423.7, "offset": -54200}
```

### A.3 対象ファイル

| Action | File | 変更内容 |
|--------|------|---------|
| MOD | `edge/lib/drivers/hx711_driver.py` | `calibrate(known_weight_g)` メソッド追加。scale 計算して返す。`save_calibration()` / `load_calibration()` で NVS (Non-Volatile Storage) に永続化 |
| MOD | `edge/office/shelf-sensor/main.py` | MCP ツール `tare` と `calibrate` を登録。起動時に NVS からキャリブレーション値をロード |
| MOD | `edge/lib/sensor_registry.py` | `hx711` ファクトリに NVS 自動ロード組み込み。`calibration_file` config フィールド追加 |
| NEW | `services/brain/src/calibration_manager.py` | `CalibrationManager` — 校正ステート管理 (2段階フロー: tare→known_weight)。device_id ごとに校正状態を追跡 |
| MOD | `services/brain/src/tool_registry.py` | `calibrate_shelf` ツール定義追加 (`device_id`, `step: tare\|set_known_weight`, `weight_g`) |
| MOD | `services/brain/src/tool_executor.py` | `_handle_calibrate_shelf()` — CalibrationManager 経由で MCP call_tool を2段階実行 |
| MOD | `services/brain/src/sanitizer.py` | `calibrate_shelf` バリデーション: weight_g > 0, step の enum チェック |
| MOD | `infra/virtual_edge/src/shelf_sensor.py` | `tare` / `calibrate` MCP ツール追加 (仮想実装) |
| NEW | `services/brain/tests/test_calibration_manager.py` | ~10 テスト: tare→calibrate フロー、不正ステップ、タイムアウト |

### A.4 Edge NVS 永続化 (MicroPython)

```python
# hx711_driver.py に追加
import json

def save_calibration(self, path="/calibration.json"):
    data = {"offset": self._offset, "scale": self._scale}
    with open(path, "w") as f:
        json.dump(data, f)

def load_calibration(self, path="/calibration.json"):
    try:
        with open(path, "r") as f:
            data = json.load(f)
        self._offset = data["offset"]
        self._scale = data["scale"]
        return True
    except (OSError, KeyError):
        return False
```

### A.5 テスト計画

| テスト | 内容 |
|--------|------|
| tare 正常系 | tare 実行後 offset が更新される |
| calibrate 正常系 | 既知重量設定後 scale が正しく計算される |
| ステップ順序エラー | tare 前に calibrate を呼ぶとエラー |
| NVS 永続化 | save → power cycle → load で値が復元される |
| 仮想デバイス | VirtualShelfSensor の tare/calibrate が正常応答を返す |

---

## B. ランタイム物品登録

### B.1 概要

現在の物品定義は `config/inventory.yaml` に静的記述。以下の2経路でランタイム登録を可能にする:

1. **Dashboard API 経由**: 管理UI から物品マスタを CRUD
2. **バーコードスキャン経由** (Phase 2): バーコード読取→JAN API で商品名自動取得→重量記録

### B.2 データモデル

```
InventoryItem (新テーブル: public.inventory_items)
├── id: int (PK)
├── device_id: str           # 紐付くセンサ
├── channel: str             # "weight"
├── zone: str
├── item_name: str
├── category: str
├── unit_weight_g: float     # 1個あたりの重量
├── tare_weight_g: float     # 容器重量
├── min_threshold: int
├── reorder_quantity: int
├── store: str (nullable)
├── price: float (nullable)
├── barcode: str (nullable)  # JAN/EAN コード
├── is_active: bool          # 有効フラグ
├── created_at: datetime
└── updated_at: datetime
```

### B.3 対象ファイル

| Action | File | 変更内容 |
|--------|------|---------|
| NEW | `services/dashboard/backend/models.py` | `InventoryItem` SQLAlchemy モデル追加 |
| NEW | `services/dashboard/backend/schemas.py` | `InventoryItemCreate` / `InventoryItemUpdate` / `InventoryItem` Pydantic スキーマ |
| NEW | `services/dashboard/backend/routers/inventory.py` | REST API: GET/POST/PUT/DELETE `/inventory/items`, GET `/inventory/items/{device_id}` |
| MOD | `services/dashboard/backend/main.py` | `inventory` ルーター登録 |
| MOD | `services/brain/src/inventory_tracker.py` | `_load_config()` を2段階に: YAML → REST API フォールバック。`reload_from_api()` メソッド追加。DB レコードを優先、YAML は初期シード |
| MOD | `services/brain/src/dashboard_client.py` | `get_inventory_items()` メソッド追加 (GET /inventory/items) |
| MOD | `services/brain/src/main.py` | 起動時に `dashboard.get_inventory_items()` → `inventory_tracker` にロード |
| NEW | `services/dashboard/backend/tests/test_inventory_endpoints.py` | ~15 テスト: CRUD、バリデーション、重複防止 |

### B.4 REST API 設計

| Method | Path | Description |
|--------|------|-------------|
| GET | `/inventory/items` | 物品マスタ一覧 (`?zone=`, `?device_id=`, `?active_only=true`) |
| POST | `/inventory/items` | 物品登録 (同一 device_id:channel の重複チェック — 複数品目モード以外) |
| PUT | `/inventory/items/{id}` | 物品更新 (unit_weight_g, tare_weight_g, min_threshold 等) |
| DELETE | `/inventory/items/{id}` | 物品削除 (soft delete: is_active=false) |
| POST | `/inventory/items/from-barcode` | Phase 2: バーコードから自動登録 |

### B.5 YAML → DB マイグレーション戦略

```
起動時:
  1. DB から inventory_items を取得
  2. DB が空なら config/inventory.yaml からシード挿入
  3. DB レコードを InventoryTracker にロード
  4. 以降の変更は DB のみ (YAML は初期テンプレートとして残す)
```

### B.6 バーコード自動登録 (Phase 2)

```
バーコードスキャナ (ESP32 + GM65) → MQTT office/{zone}/sensor/{device_id}/barcode {"value": "4901234567890"}
    ↓
WorldModel._update_environment() → channel=="barcode" 判定
    ↓
InventoryTracker.register_barcode(device_id, channel, barcode, current_weight)
    ↓
(Optional) JAN API lookup: https://api.jancode.net/v1/{code} → 商品名
    ↓
Dashboard POST /inventory/items/from-barcode → DB 登録
    ↓
InventoryTracker に新品目を追加 → 以降は重量変化で消費追跡
```

### B.7 テスト計画

| テスト | 内容 |
|--------|------|
| CRUD 正常系 | 物品の作成・取得・更新・削除 |
| 重複防止 | 同一 device_id:channel に複数登録でエラー (単品モード時) |
| YAML シード | DB空→YAML読み込み→DB挿入 |
| reload_from_api | API 経由で InventoryTracker の設定を動的更新 |
| バーコード登録 | POST /inventory/items/from-barcode でDB登録 + tracker更新 |

---

## C. 1センサ複数品目管理

### C.1 概要

現実の棚では複数品目が混在する。1つの重量センサで複数品目を管理するには、品目の入出を別の手段で識別する必要がある。

### C.2 アプローチ比較

| 方式 | 仕組み | 精度 | コスト | 適用場面 |
|------|--------|------|--------|---------|
| **C-1: 区画分割** | 物理的に棚を区画に分け、各区画に独立したロードセル | 高 | 高 (ロードセル×区画数) | 固定品目の定位置管理 |
| **C-2: バーコードハイブリッド** | バーコードで品目特定 + 重量差分で数量追跡 | 中〜高 | 中 (バーコードスキャナ追加) | 品目が頻繁に変わる棚 |
| **C-3: 推定モデル** | 品目の重量パターンを学習して推定 | 低〜中 | 低 (追加HW不要) | 品目数が少なく重量差が大きい場合 |

**推奨**: **C-2 (バーコードハイブリッド)** を主軸とし、C-1 は物理設計として並行対応。

### C.3 C-2: バーコードハイブリッド方式 詳細設計

#### データフロー

```
[入庫フロー]
ユーザー: 商品のバーコードをスキャン → ESP32/GM65
    ↓
MQTT: office/{zone}/sensor/{device_id}/barcode {"value": "4901234567890"}
    ↓
InventoryTracker.handle_barcode_scan(device_id, barcode)
    ↓
  1. barcode → item_name 解決 (ローカルDB or JAN API)
  2. 現在の重量を記録 (weight_before)
  3. 安定待ち (3秒後に再測定)
  4. weight_after - weight_before = item_weight_g
  5. CompartmentState に品目追加 {barcode, item_name, weight_g, quantity}
    ↓
イベント: "item_added" → WorldModel

[消費フロー]
重量センサ: 重量が減少
    ↓
InventoryTracker.update_weight()
    ↓
  1. weight_delta = prev_weight - current_weight
  2. CompartmentState の品目リストから最も近い unit_weight を持つ品目を特定
  3. 該当品目の quantity を減算
  4. quantity < min_threshold → "low_stock" イベント
    ↓
Brain → add_shopping_item (品目名付き)
```

#### データモデル拡張

```python
@dataclass
class CompartmentItem:
    """棚上の個別品目。"""
    barcode: Optional[str]
    item_name: str
    unit_weight_g: float          # スキャン時に実測 or DB参照
    quantity: int
    total_weight_g: float         # quantity × unit_weight_g
    min_threshold: int = 1
    reorder_quantity: int = 1
    category: str = ""
    store: Optional[str] = None
    price: Optional[float] = None
    last_scan_time: float = 0.0

@dataclass
class ShelfState:
    """Runtime state — 単品モードと複数品目モードの両方をサポート。"""
    current_weight_g: Optional[float] = None
    readings: List[float] = field(default_factory=list)
    last_low_stock_time: float = 0.0
    prev_quantity: Optional[int] = None        # 単品モード用
    # 複数品目モード
    items: List[CompartmentItem] = field(default_factory=list)
    mode: str = "single"                       # "single" | "multi"
    prev_total_weight_g: Optional[float] = None
```

#### 消費品目の推定ロジック

```python
def _estimate_consumed_item(self, weight_delta_g: float, items: List[CompartmentItem]) -> Optional[CompartmentItem]:
    """重量減少から消費された品目を推定する。

    戦略:
    1. weight_delta に最も近い unit_weight を持つ品目を選択
    2. 複数候補がある場合は quantity が最も少ない品目を優先
       (在庫が少ない品目が先に消費される可能性が高い)
    3. 誤差許容: unit_weight の ±30% 以内
    """
    if not items or weight_delta_g <= 0:
        return None

    candidates = []
    for item in items:
        if item.quantity <= 0:
            continue
        ratio = weight_delta_g / item.unit_weight_g
        n_units = round(ratio)
        if n_units >= 1:
            error_pct = abs(weight_delta_g - n_units * item.unit_weight_g) / item.unit_weight_g * 100
            if error_pct <= 30:
                candidates.append((item, n_units, error_pct))

    if not candidates:
        return None

    # Sort by error, then by quantity ascending (low stock first)
    candidates.sort(key=lambda x: (x[2], x[0].quantity))
    return candidates[0][0]
```

### C.4 対象ファイル

| Action | File | 変更内容 |
|--------|------|---------|
| MOD | `services/brain/src/inventory_tracker.py` | `ShelfState` に `items: List[CompartmentItem]` と `mode` 追加。`handle_barcode_scan()` 実装。`update_weight()` にマルチ品目消費推定ロジック追加。`_estimate_consumed_item()` 実装 |
| MOD | `services/brain/src/world_model/world_model.py` | `_update_environment()` に `barcode` チャネル判定追加 → `inventory_tracker.handle_barcode_scan()` |
| MOD | `config/inventory.yaml` | `mode: single\|multi` フィールド追加。multi モードの棚は `items` を空リストで初期化 |
| NEW | `edge/lib/drivers/gm65_driver.py` | GM65 バーコードスキャナ UART ドライバ (MicroPython) |
| MOD | `edge/lib/sensor_registry.py` | `gm65` ファクトリ追加 |
| NEW | `edge/office/shelf-sensor-multi/main.py` + `config.json` | HX711 + GM65 統合ノード。バーコードスキャン時にバーコード+現在重量を同時送信 |
| MOD | `services/brain/src/tool_registry.py` | `check_inventory` レスポンスに品目別内訳を追加 |
| MOD | `infra/virtual_edge/src/shelf_sensor.py` | バーコードスキャンシミュレーション追加 (ランダムタイミングで JAN コード送信) |
| NEW | `services/brain/tests/test_inventory_multi_item.py` | ~20 テスト: バーコードスキャン→品目追加、重量減→消費推定、複数品目の低在庫、推定誤差境界 |

### C.5 テスト計画

| テスト | 内容 |
|--------|------|
| バーコードスキャン→品目追加 | scan 後に items リストに追加される |
| 重量差分→品目推定 | 200g 減少 → 200g/個の品目が消費と判定 |
| 複数候補の優先度 | 同重量品目が2つある場合、在庫が少ない方を選択 |
| 誤差許容 | unit_weight ±30% 以内はマッチ、超過は不一致 |
| 複数品目同時低在庫 | 2品目が同時に閾値以下 → 2件の low_stock イベント |
| single → multi モード遷移 | バーコードスキャンで自動的に multi モードに切替 |
| multi モードの restock | バーコードスキャン+重量増加 → 該当品目の quantity 増加 |

---

## 実装優先度

| 順序 | 課題 | 理由 |
|------|------|------|
| **1** | A. キャリブレーション | センサ精度の基盤。これなしでは B/C の精度が出ない |
| **2** | B. ランタイム物品登録 | 運用ハードルを下げる。YAML 手動編集からの脱却 |
| **3** | C. マルチアイテム | B のバーコード登録基盤に依存。最も複雑だが価値も大きい |

### 依存関係

```
A. キャリブレーション ──→ (精度が保証された重量データ)
                              ↓
B. ランタイム物品登録 ──→ (DB ベースの品目マスタ + バーコード→品目解決)
                              ↓
C. マルチアイテム ────→ (バーコード + 重量差分 = 品目別追跡)
```

---

## 見積もり

| 課題 | 新規ファイル | 修正ファイル | テスト数 |
|------|-------------|-------------|---------|
| A | 2 (CalibrationManager, test) | 5 (hx711, shelf main, registry, tool_reg, tool_exec) | ~10 |
| B | 3 (model, router, test) | 5 (schemas, main, tracker, dashboard_client, brain main) | ~15 |
| C | 3 (gm65 driver, shelf-multi, test) | 5 (tracker, world_model, yaml, tool_reg, virtual) | ~20 |
| **合計** | **8** | **15** (重複除く ~10) | **~45** |
