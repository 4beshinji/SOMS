# Shelf Scale C6 — HX711 + XIAO ESP32-C6

5KG ロードセルによる在庫重量監視デバイス。

## 配線

```
XIAO ESP32-C6          HX711 Board              5KG Load Cell
+---------+            +-----------+            +----------+
| 5V   ───┼──────────> | VCC       |            |          |
| GND  ───┼──────────> | GND       |            |          |
| D2   ───┼──────────> | DT (DOUT) |            |          |
| D3   ───┼──────────> | SCK       |            |          |
+---------+            |           |            |          |
                       | E+  ──────┼──────────> | 赤 (E+)  |
                       | E-  ──────┼──────────> | 黒 (E-)  |
                       | A+  ──────┼──────────> | 緑 (S+)  |
                       | A-  ──────┼──────────> | 白 (S-)  |
                       +-----------+            +----------+
```

### 注意事項

- **VCC は 5V 必須** — 3.3V だと ADC が飽和する場合がある
- **A+/A- の色**: Amazon B098Q2FVW1 のモジュールは A+=緑, A-=白 (一般的な配色と逆)
- ボード上のシルク印刷 (GND / DT / SCK / VCC) に従うこと
- ロードセル到着時にテスターで確認: 赤-緑, 赤-白 ≈ 750Ω / 赤-黒, 白-緑 ≈ 1kΩ

## フラッシュ

```bash
# config.json の WiFi/MQTT を編集してから実行
./flash.sh              # ポート自動検出
./flash.sh /dev/ttyACM0 # ポート指定
./flash.sh --libs-only  # コードのみ更新 (MicroPython 再フラッシュ不要)
```

前提: `uv pip install esptool mpremote --python .venv/bin/python`

## キャリブレーション

```
mpremote connect /dev/ttyACM0

>>> from lib.drivers.hx711_driver import HX711
>>> hx = HX711(2, 3)
>>> hx.is_ready()          # True であること
>>> hx.tare(20)            # 空荷でゼロ調整
>>> # 既知重量 (例: 500g) を載せる
>>> hx.calibrate(500, 10)  # スケールファクタ算出
>>> hx.save_calibration()  # /calibration.json に保存
```

MCP リモートキャリブレーション:
```bash
# tare
mosquitto_pub -h <broker> -t 'mcp/scale_01/request/call_tool' \
  -m '{"jsonrpc":"2.0","method":"call_tool","params":{"name":"tare","arguments":{}},"id":"t1"}'

# calibrate (500g)
mosquitto_pub -h <broker> -t 'mcp/scale_01/request/call_tool' \
  -m '{"jsonrpc":"2.0","method":"call_tool","params":{"name":"calibrate","arguments":{"known_weight_g":500}},"id":"c1"}'

# レスポンス確認
mosquitto_sub -h <broker> -t 'mcp/scale_01/response/#' -v
```

## MQTT トピック

```
office/kitchen/sensor/scale_01/weight    {"value": 342.5}
office/kitchen/sensor/scale_01/heartbeat {"status":"online","uptime_sec":...}
```

## ステータス

**開発一時中止** — ロードセル内部断線 (赤-緑間 3.2MΩ、正常 ~750Ω)。交換待ち。
XIAO + HX711 の通信は正常確認済み。
