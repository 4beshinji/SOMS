# Brain Service

SOMS の中央知性。ReAct (Reason + Act) 認知ループで LLM を駆動し、センサーデータと映像情報から自律的にオフィス環境を管理する。

## 概要

- **LLM**: Ollama (Qwen2.5 等) または Mock LLM
- **ループ**: 30秒ポーリング + MQTT イベントトリガー (3秒バッチ遅延)
- **最大反復**: 1サイクル 5イテレーション
- **ポート**: 8080 (`chat_server.py` — chat / `/devices/status` / Ollama モデル管理)。Dashboard API / Voice API を REST クライアントとしても呼び出す

## ReAct 認知ループ

```
MQTT イベント / 30秒タイマー
        ↓
[Think]  LLM にゾーン状態・センサーデータ・過去アクション履歴を入力
        ↓
[Act]    tool_call を受け取り ToolExecutor で実行
        ↓
[Observe] ツール結果を LLM フィードバックとして追記
        ↓ (最大5回)
終了 (tool_call なし or 最大反復到達)
```

## ファイル構成

```
services/brain/src/
├── main.py                 Brain クラス (MQTT ハンドラ + ReAct ループ)
├── llm_client.py           OpenAI 互換 API ラッパー (aiohttp, 120s タイムアウト)
├── tool_registry.py        OpenAI function-calling スキーマ定義
├── tool_executor.py        ツール実行・ルーティング (sanitizer 経由)
├── sanitizer.py            入力バリデーション・セキュリティ
├── system_prompt.py        Constitutional AI システムプロンプト生成
├── dashboard_client.py     Dashboard REST クライアント
├── mcp_bridge.py           MQTT ↔ JSON-RPC 2.0 翻訳 (10s タイムアウト)
├── device_registry.py      デバイス登録・トラスト管理 (in-memory、GET /devices/status で公開)
├── chat_server.py          aiohttp HTTP サーバ (chat / device health / model mgmt、port 8080)
├── task_reminder.py        タスク再アナウンス (1時間後、30分クールダウン)
├── spatial_config.py       YAML 空間設定ローダー (Backend REST フォールバック)
├── federation_config.py    リージョン設定ローダー
├── event_store/
│   ├── writer.py           PostgreSQL へのセンサー/LLM イベント書き込み
│   └── aggregator.py       10分毎の時系列集計
└── world_model/
    ├── world_model.py      WorldModel クラス (ゾーン状態管理)
    ├── data_classes.py     ZoneState, EnvironmentData, OccupancyData 等
    └── sensor_fusion.py    指数減衰重み付け融合
```

## LLM ツール

| ツール | 用途 | 主なパラメータ |
|--------|------|--------------|
| `create_task` | ダッシュボードにタスク作成 | title, description, urgency (0-4), zone, task_types, audience, skill_level (任意) |
| `send_device_command` | MCP 経由でエッジデバイス制御 | agent_id, tool_name, arguments |
| `get_zone_status` | WorldModel からゾーン状態取得 | zone_id |
| `speak` | 音声アナウンス (ダッシュボード不使用) | message (70文字以内), zone, tone |
| `get_active_tasks` | アクティブタスク一覧 (重複防止) | — |
| `get_device_status` | デバイスの接続・バッテリー状態 | zone_id (省略可) |

### ツールを追加する

1. `tool_registry.py` に OpenAI function-calling スキーマを追加:

```python
{
    "type": "function",
    "function": {
        "name": "my_new_tool",
        "description": "...",
        "parameters": {
            "type": "object",
            "properties": {
                "param_a": {"type": "string", "description": "..."},
            },
            "required": ["param_a"],
        },
    },
}
```

2. `tool_executor.py` の `execute_tool()` に分岐を追加:

```python
elif tool_name == "my_new_tool":
    return await self._handle_my_new_tool(arguments)
```

3. `_handle_my_new_tool()` メソッドを実装:

```python
async def _handle_my_new_tool(self, args: Dict[str, Any]) -> Dict[str, Any]:
    param_a = args.get("param_a", "")
    # ... 実装 ...
    return {"success": True, "result": "..."}
```

## WorldModel

`WorldModel` は MQTT メッセージをリアルタイムで処理し、全ゾーンの統合状態を管理する。

### ゾーン状態 (`ZoneState`)

```python
ZoneState:
  zone_id: str                    # e.g., "main", "meeting_room_a"
  environment: EnvironmentData    # 温度・湿度・CO2・照度
  occupancy: OccupancyData        # 人数・活動レベル・姿勢
  devices: Dict[str, DeviceState] # デバイス ID → 状態
  spatial: ZoneSpatialData        # ライブ検出・ヒートマップ
  metadata: ZoneMetadata          # ポリゴン・面積・隣接ゾーン
  tracking: TrackingData          # クロスカメラ追跡
  events: List[Event]             # 直近イベント履歴
```

### センサー融合

指数減衰重み付けで複数センサーの値を融合:

| チャネル | 半減期 |
|---------|--------|
| temperature | 2分 |
| co2 | 1分 |
| occupancy | 30秒 |

### 空間設定の取得順序

```
1. DashboardClient.get_spatial_config()  (GET /sensors/spatial/config)
   → Layer1 (YAML) + Layer2 (DB) がマージされた状態で取得
2. 失敗時: load_spatial_config("config/spatial.yaml")  (直接ロード)
```

## タスク重複防止

- **Stage 1**: title + location の完全一致
- **Stage 2**: zone + task_type の一致
- アクティブタスクは `get_active_tasks` ツールで LLM が確認できる

## イベントストア

MQTT センサーデータと LLM 決定履歴を PostgreSQL に記録。

```sql
events.raw_events           -- センサー生データ (BRIN インデックス)
events.llm_decisions        -- ReAct サイクル結果
events.hourly_aggregates    -- 1時間毎集計
events.spatial_snapshots    -- カメラ検出スナップショット
events.spatial_heatmap_hourly  -- 占有ヒートマップ集計
```

データ保持: 730日 (ML 季節パターン学習用)

## 設定

| 環境変数 | デフォルト | 説明 |
|---------|-----------|------|
| `LLM_API_URL` | `http://mock-llm:8000/v1` | LLM API エンドポイント |
| `LLM_MODEL` | (Ollama モデル名) | 使用モデル |
| `MQTT_BROKER` | `mosquitto` | MQTT ブローカーホスト |
| `MQTT_PORT` | `1883` | MQTT ポート |
| `MQTT_USER` / `MQTT_PASS` | `soms` / `soms_dev_mqtt` | MQTT 認証 |
| `DASHBOARD_API_URL` | `http://backend:8000` | Dashboard API URL |
| `DATABASE_URL` | (PostgreSQL) | イベントストア用 DB |

## ログ確認

```bash
docker logs -f soms-brain
```

認知サイクル開始時に `ReAct cycle triggered` が出力される。ツール呼び出しは `Tool call: <name>` で追跡可能。
