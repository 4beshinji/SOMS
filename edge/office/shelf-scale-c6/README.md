# Shelf Scale C6 — HX711 + XIAO ESP32-C6

5KG ロードセルによる在庫重量監視デバイス。SOMS の InventoryTracker と連携し、棚上アイテムの個数を自動追跡する。

## 配線

```
XIAO ESP32-C6          HX711 Board              5KG Load Cell
+---------+            +-----------+            +----------+
| 5V   ───┼──────────> | VCC       |            |          |
| GND  ───┼──────────> | GND       |            |          |
| D4   ───┼──────────> | DT (DOUT) |            |          |
| D5   ───┼──────────> | SCK       |            |          |
+---------+            |           |            |          |
  (GPIO22=DT)          | E+  ──────┼──────────> | 赤 (E+)  |
  (GPIO23=SCK)         | E-  ──────┼──────────> | 黒 (E-)  |
                       | A+  ──────┼──────────> | 緑 (S+)  |
                       | A-  ──────┼──────────> | 白 (S-)  |
                       +-----------+            +----------+
```

### ピン選定の注意

- **D4/D5 (GPIO22/23) を使用すること。** D2/D3 (GPIO2/3) は XIAO ESP32-C6 の MicroPython で HX711 と正常に通信できない (DOUT がフローティングになる)
- XIAO のシルク印刷 D4 = GPIO22、D5 = GPIO23

### 配線の注意

- **VCC は 5V 必須** — 3.3V だと ADC が飽和する場合がある
- **A+/A- の色**: Amazon B098Q2FVW1 のモジュールは A+=緑, A-=白 (一般的な配色と逆)
- ボード上のシルク印刷 (GND / DT / SCK / VCC) に従うこと
- ロードセルのテスター確認値: 赤-緑, 赤-白 ≈ 750Ω / 赤-黒, 白-緑 ≈ 1kΩ
- スケールファクタが負の値になるのはロードセル極性逆のためで、動作に影響なし

## フラッシュ

```bash
# config.json の WiFi/MQTT を編集してから実行
./flash.sh              # ポート自動検出
./flash.sh /dev/ttyACM0 # ポート指定
./flash.sh --libs-only  # コードのみ更新 (MicroPython 再フラッシュ不要)
```

前提: `uv pip install esptool mpremote --python .venv/bin/python`

## キャリブレーション

**重要**: タレとキャリブレーションは別々の exec で実行すること。1回の exec 内で「ユーザーに物を載せてもらう」ような待機を入れると、出力が見えないため指示に従えない。

### Step 1: タレ (空荷)

```bash
mpremote connect /dev/ttyACM0 exec "
from lib.drivers.hx711_driver import HX711
import time
hx = HX711(22, 23)
for _ in range(5):
    try: hx._read_raw()
    except: pass
    time.sleep_ms(100)
hx.tare(20)
hx.save_calibration()
print('offset =', hx.get_calibration()['offset'])
"
```

### Step 2: 既知重量を載せてキャリブレーション

```bash
# 例: 193.8g の物体を載せた状態で実行
mpremote connect /dev/ttyACM0 exec "
from lib.drivers.hx711_driver import HX711
import time
hx = HX711(22, 23)
for _ in range(5):
    try: hx._read_raw()
    except: pass
    time.sleep_ms(100)
hx.load_calibration()
scale = hx.calibrate(193.8, readings=20)
print('scale =', scale)
hx.save_calibration()
for i in range(5):
    w = hx.read_weight(5)
    print(round(w, 1), 'g')
    time.sleep_ms(300)
"
```

### Step 3: 検証 (空荷)

```bash
mpremote connect /dev/ttyACM0 exec "
from lib.drivers.hx711_driver import HX711
import time
hx = HX711(22, 23)
for _ in range(5):
    try: hx._read_raw()
    except: pass
    time.sleep_ms(100)
hx.load_calibration()
for i in range(5):
    w = hx.read_weight(5)
    print(round(w, 1), 'g')
    time.sleep_ms(300)
"
```

### MCP リモートキャリブレーション (MQTT 接続時)

```bash
# tare
mosquitto_pub -h <broker> -t 'mcp/scale_01/request/call_tool' \
  -m '{"jsonrpc":"2.0","method":"call_tool","params":{"name":"tare","arguments":{}},"id":"t1"}'

# calibrate
mosquitto_pub -h <broker> -t 'mcp/scale_01/request/call_tool' \
  -m '{"jsonrpc":"2.0","method":"call_tool","params":{"name":"calibrate","arguments":{"known_weight_g":193.8}},"id":"c1"}'

# レスポンス確認
mosquitto_sub -h <broker> -t 'mcp/scale_01/response/#' -v
```

## 在庫管理との統合

### データフロー

```
HX711 → main.py (MQTT publish)
  → office/kitchen/sensor/scale_01/weight {"value": 193.8}
  → WorldModel (sensor fusion)
  → InventoryTracker (重量→数量変換)
  → Brain LLM コンテキスト ("⚠️ 残量0冊")
  → LLM が add_shopping_item / create_task を呼ぶ
```

### 在庫設定 (`config/inventory.yaml`)

```yaml
- device_id: scale_01
  channel: weight
  zone: kitchen
  item_name: クーデター――政権転覆のメカニズム
  unit_weight_g: 193.8
  tare_weight_g: 0.0
  min_threshold: 1
```

InventoryTracker は `quantity = int((weight - tare_weight_g) / unit_weight_g)` で個数を算出。`min_threshold` 未満で `low_stock` イベントを発火する (1時間クールダウン)。

### 有線テスト (USB ブリッジ)

MQTT なしで InventoryTracker の動作を検証するテストツール:

```bash
.venv/bin/python -u edge/tools/test_inventory_bridge.py --interval 3
```

USB 経由で HX711 の重量を読み、ホスト側の InventoryTracker に渡して `qty` と `low_stock` イベントを表示する。

## MQTT トピック

```
office/kitchen/sensor/scale_01/weight    {"value": 193.8}
office/kitchen/sensor/scale_01/heartbeat {"status":"online","uptime_sec":...}
```

## キャリブレーション実績

| 日付 | 基準物体 | scale | 精度 | 備考 |
|------|---------|-------|------|------|
| 2026-04-09 | 中公新書 193.8g | -16682.7 | ±0.3g | USB 直結テスト |
| 2026-04-09 | 中公新書 193.8g | -15119.06 | ±2g | WiFi/MQTT E2E テスト |

## ステータス

**WiFi/MQTT E2E 動作確認済み** — HX711 通信・キャリブレーション・NVS 永続化・InventoryTracker 統合テスト・WiFi/MQTT テレメトリ送信・MCP リモートツールコール、すべて動作確認完了。
