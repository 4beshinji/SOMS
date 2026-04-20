> ⚠️ **v2 B2B note**: this document predates the v2 fork and may reference the v1 credit economy (wallet, XP, bounty, demurrage). Those features are removed on `main`. See [`docs/architecture/v2-b2b-migration.md`](../architecture/v2-b2b-migration.md) for the current architecture. v1 is preserved at branch `legacy/v1-with_wallet` / tag `v1.0-with_wallet`.

# 参加ガイド

SOMSは誰でも参加できる。コードを書く必要すらない。

---

## 参加方法

### 1. センサーを設置する (最も簡単)

ESP32 + センサーモジュール (数百円〜) を既存のCoreHubに接続するだけ。

```bash
# MQTTで {"value": X} を送るだけでCoreHubが自動認識
mosquitto_pub -h <hub_ip> -u soms -P soms_dev_mqtt \
  -t 'office/my_zone/sensor/my_device/temperature' \
  -m '{"value": 23.5}'
```

- CoreHubのWorldModelが即座にセンサーを認識
- デバイスXPが自動蓄積 → 報酬乗数が上昇
- SensorSwarm (ESP-NOW/UART/I2C/BLE) でWiFi不要のメッシュ網も構築可能

### 2. 自分のCoreHubをデプロイする

GPUマシンがあれば、完全に独立した自律知能ノードを立ち上げられる。

```bash
git clone <repository_url> && cd Office_as_AI_ToyBox
cp env.example .env

# シミュレーション (GPUなし)
./infra/scripts/start_virtual_edge.sh

# 本番 (AMD ROCm GPU)
docker compose -f infra/docker-compose.yml up -d --build
```

あなたのCoreHubは即座に自律動作を開始し、センサーを自動検出する。

### 3. GPUマシンを提供する

既存のCoreHubにGPUリソースを提供する場合、インフラ報酬 (5,000/時) が発行される。

### 4. タスクを遂行する

CoreHubのLLMが検知した物理タスク (換気、清掃、備品補充など) を実行すると、クレジット報酬 (500〜5,000) を受け取れる。

### 5. コードを貢献する

以下のセクションを参照。

---

## コード貢献

### よくある拡張パターン

1. [LLM ツールを追加する](#1-llm-ツールを追加する)
2. [MQTT トピックを追加する](#2-mqtt-トピックを追加する)
3. [Perception モニターを追加する](#3-perception-モニターを追加する)
4. [Dashboard API エンドポイントを追加する](#4-dashboard-api-エンドポイントを追加する)
5. [新しいサービスを追加する](#5-新しいサービスを追加する)

---

## 1. LLM ツールを追加する

Brain が LLM から呼び出せるツールを追加する。

### ステップ 1: スキーマ定義 (`tool_registry.py`)

```python
# services/brain/src/tool_registry.py の get_tools() リストに追加
{
    "type": "function",
    "function": {
        "name": "check_supply_level",
        "description": "消耗品の在庫レベルを確認する",
        "parameters": {
            "type": "object",
            "properties": {
                "item_name": {
                    "type": "string",
                    "description": "確認する消耗品の名前"
                },
                "zone": {
                    "type": "string",
                    "description": "対象ゾーン"
                },
            },
            "required": ["item_name"],
        },
    },
}
```

### ステップ 2: 実行ルーティング (`tool_executor.py`)

```python
elif tool_name == "check_supply_level":
    return await self._handle_check_supply_level(arguments)
```

### ステップ 3: ハンドラー実装

```python
async def _handle_check_supply_level(self, args: Dict[str, Any]) -> Dict[str, Any]:
    item_name = args.get("item_name", "")
    zone = args.get("zone", "main")
    level = await self._fetch_supply_level(item_name, zone)
    return {"success": True, "result": f"{item_name}: 残量 {level}%"}
```

### ステップ 4: システムプロンプトに追記 (必要な場合)

`system_prompt.py` の `build_system_message()` にツールの使用指針を追加。

---

## 2. MQTT トピックを追加する

### トピック命名規則

```
office/{zone}/{device_type}/{device_id}/{channel}
```

### ペイロード形式

センサー値は必ず以下の形式 (WorldModel 互換):

```json
{"value": 42.5}
```

WorldModel の `update_from_mqtt()` がトピックをパースして自動マッピングする。

新しいチャネルを追加する場合:
1. `services/brain/src/world_model/world_model.py` の CHANNEL_MAP に追加
2. `services/brain/src/world_model/data_classes.py` の `EnvironmentData` にフィールド追加

---

## 3. Perception モニターを追加する

### ステップ 1: Monitor クラスを作成

`services/perception/src/monitors/` に `MonitorBase` を継承したクラスを作成。

### ステップ 2: monitors.yaml に設定を追加

```yaml
monitors:
  - name: my_new_monitor
    type: MyNewMonitor
    camera_id: camera_node_01
    zone_name: main
    enabled: true
```

### ステップ 3: MonitorFactory に登録

`services/perception/src/monitor_factory.py` の `MONITOR_REGISTRY` に追加。

---

## 4. Dashboard API エンドポイントを追加する

1. `services/dashboard/backend/routers/` にルーターファイルを作成
2. `services/dashboard/backend/main.py` で `app.include_router()` で登録
3. モデルが必要なら `models.py` に追加 (起動時に自動テーブル作成)

---

## 5. 新しいサービスを追加する

1. `services/my-service/` ディレクトリを作成 (`src/main.py` + `Dockerfile`)
2. `infra/docker-compose.yml` にサービス定義を追加
3. `CLAUDE.md` の Service Ports テーブルと nginx conf を更新

---

## git ワークフロー

### コミットスタイル

```
feat: 新機能を追加
fix: バグを修正
docs: ドキュメントを更新
refactor: リファクタリング (機能変更なし)
chore: 設定・ツール変更
```

bilingual (英語コード + 日本語説明) も可。

### 並行開発

`docs/parallel-dev/WORKER_GUIDE.md` を参照。git worktree を使用する。

### コミット前チェック

```bash
# テスト実行
for d in services/brain/tests services/auth/tests services/voice/tests \
  services/dashboard/backend/tests services/wallet/tests \
  services/switchbot/tests services/perception/tests; do
  .venv/bin/python -m pytest "$d" --tb=short
done

# フロントエンド
cd services/dashboard/frontend && pnpm run build
```
