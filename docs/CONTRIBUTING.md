# コントリビューションガイド

SOMS への変更を加える際の手順書。よくある拡張パターンをステップバイステップで説明する。

## 目次

1. [LLM ツールを追加する](#1-llm-ツールを追加する)
2. [MQTT トピックを追加する](#2-mqtt-トピックを追加する)
3. [Perception モニターを追加する](#3-perception-モニターを追加する)
4. [Dashboard API エンドポイントを追加する](#4-dashboard-api-エンドポイントを追加する)
5. [新しいサービスを追加する](#5-新しいサービスを追加する)
6. [git ワークフロー](#6-git-ワークフロー)

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
                    "description": "確認する消耗品の名前 (例: 'コーヒー豆', 'トイレットペーパー')"
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
# execute_tool() メソッドの elif チェーンに追加

elif tool_name == "check_supply_level":
    return await self._handle_check_supply_level(arguments)
```

### ステップ 3: ハンドラー実装 (`tool_executor.py`)

```python
async def _handle_check_supply_level(self, args: Dict[str, Any]) -> Dict[str, Any]:
    item_name = args.get("item_name", "")
    zone = args.get("zone", "main")

    # 実際の実装 (例: 外部 API 呼び出しや WorldModel 参照)
    level = await self._fetch_supply_level(item_name, zone)

    return {
        "success": True,
        "result": f"{item_name}: 残量 {level}%"
    }
```

### ステップ 4: システムプロンプトに追記 (必要な場合)

`system_prompt.py` の `build_system_message()` にツールの使用指針を追加。

---

## 2. MQTT トピックを追加する

新しいセンサーチャネルやデバイスタイプの MQTT トピックを追加する。

### トピック命名規則

```
office/{zone}/{device_type}/{device_id}/{channel}
```

例:
- `office/main/sensor/air_quality_01/pm25`
- `office/main/relay/light_switch_01/state`

### ペイロード形式

センサー値は必ず以下の形式で送信 (WorldModel 互換):

```json
{"value": 42.5}
```

### WorldModel での処理確認

`world_model.py` の `update_from_mqtt()` がトピックをパースして自動的に
`EnvironmentData` フィールドにマッピングする。

新しいチャネルを追加する場合:

```python
# services/brain/src/world_model/world_model.py
# update_from_mqtt() 内の channel → field マッピングを確認

CHANNEL_MAP = {
    "temperature": "temperature",
    "humidity": "humidity",
    "co2": "co2",
    "pm25": "pm25",          # 追加例
    "illuminance": "illuminance",
}
```

対応する `EnvironmentData` フィールドが `data_classes.py` に存在することを確認:

```python
# services/brain/src/world_model/data_classes.py
class EnvironmentData(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    co2: Optional[int] = None
    pm25: Optional[float] = None    # 追加
    ...
```

### イベントストアへの記録

`event_store/writer.py` は `office/{zone}/sensor/{device_id}/{channel}` 形式のトピックを
自動的に `events.raw_events` に記録する。追加設定不要。

---

## 3. Perception モニターを追加する

YOLOv11 を使った新しい検出モニターを追加する。

### ステップ 1: Monitor クラスを作成

```python
# services/perception/src/monitors/whiteboard_monitor.py を参考に

from .monitor_base import MonitorBase
import asyncio

class MyNewMonitor(MonitorBase):
    """新しいモニターの説明。"""

    def __init__(self, config: dict, mqtt_client):
        super().__init__(config, mqtt_client)
        self.threshold = config.get("threshold", 0.5)

    async def process_frame(self, frame):
        """フレームを処理してイベントを発行する。"""
        # YOLO 推論
        results = self.model(frame)

        # 結果を MQTT に発行
        if self._should_publish(results):
            await self.publish(
                topic=f"office/{self.zone}/my_monitor/{self.camera_id}",
                payload={"detected": True, "confidence": 0.9}
            )
```

### ステップ 2: monitors.yaml に設定を追加

```yaml
# services/perception/config/monitors.yaml

monitors:
  - name: my_new_monitor
    type: MyNewMonitor           # クラス名
    camera_id: camera_node_01
    zone_name: main
    enabled: true
    threshold: 0.7               # モニター固有の設定
```

### ステップ 3: MonitorFactory に登録

```python
# services/perception/src/monitor_factory.py

from monitors.my_new_monitor import MyNewMonitor

MONITOR_REGISTRY = {
    "OccupancyMonitor": OccupancyMonitor,
    "WhiteboardMonitor": WhiteboardMonitor,
    "ActivityMonitor": ActivityMonitor,
    "TrackingMonitor": TrackingMonitor,
    "MyNewMonitor": MyNewMonitor,   # 追加
}
```

---

## 4. Dashboard API エンドポイントを追加する

Backend に新しい REST エンドポイントを追加する。

### ステップ 1: ルーターファイルを作成

```python
# services/dashboard/backend/routers/my_feature.py

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db

router = APIRouter(prefix="/my-feature", tags=["my-feature"])

class MyResponse(BaseModel):
    id: int
    value: str

@router.get("/", response_model=list[MyResponse])
async def list_items(db: AsyncSession = Depends(get_db)):
    """アイテム一覧を取得する。"""
    ...
```

### ステップ 2: main.py に登録

```python
# services/dashboard/backend/main.py

from routers import tasks, users, voice_events, sensors, spatial, devices, spaces, my_feature

app.include_router(my_feature.router)
```

### ステップ 3: モデルが必要な場合

```python
# services/dashboard/backend/models.py に追加

class MyModel(Base):
    __tablename__ = "my_models"
    id = Column(Integer, primary_key=True)
    value = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

SQLAlchemy の `Base.metadata.create_all()` が起動時に自動実行されるので
Alembic マイグレーション不要 (開発環境)。

---

## 5. 新しいサービスを追加する

完全に新しいマイクロサービスを追加する。

### ステップ 1: サービスディレクトリを作成

```
services/my-service/
├── src/
│   ├── main.py        FastAPI エントリーポイント
│   └── ...
├── Dockerfile
└── README.md          ← 必ず作成する
```

### ステップ 2: Dockerfile

既存サービスのパターンに従う:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### ステップ 3: docker-compose.yml に追加

```yaml
# infra/docker-compose.yml

my-service:
  container_name: soms-my-service
  build:
    context: ../services/my-service
    dockerfile: Dockerfile
  volumes:
    - ../services/my-service/src:/app
  environment:
    - DATABASE_URL=${DATABASE_URL}
  ports:
    - "127.0.0.1:80XX:8000"   # ポート番号は CLAUDE.md の Service Ports テーブルに追記
  depends_on:
    - postgres
  restart: unless-stopped
```

### ステップ 4: CLAUDE.md と nginx を更新

- `CLAUDE.md` の Service Ports テーブルに新ポートを追記
- `services/dashboard/frontend/nginx.conf` に必要なプロキシルールを追加
- `services/my-service/README.md` を作成

---

## 6. git ワークフロー

### ブランチ戦略

並行開発する場合は `docs/parallel-dev/WORKER_GUIDE.md` を参照。
単独作業の場合は main ブランチに直接コミット可能。

### コミットスタイル

```
feat: 新機能を追加
fix: バグを修正
docs: ドキュメントを更新
refactor: リファクタリング (機能変更なし)
chore: 設定・ツール変更
```

bilingual (英語コード + 日本語説明) も可:

```
feat: add CO2 trend analysis to get_zone_status

CO2の時系列トレンド (上昇/安定/下降) をWorldModelで計算し
get_zone_statusツールの出力に追加。換気判断の精度向上。
```

### コミット前チェック

```bash
# Python 型チェック (mypy がある場合)
cd services/brain && mypy src/

# フロントエンド型チェック
cd services/dashboard/frontend && pnpm run build

# テスト実行
.venv/bin/python infra/tests/integration/test_sensor_api.py
```

### push 前の注意事項

- `main` へのリモートに先行コミットがある場合は必ず `git pull --rebase` してから push
- 破壊的変更 (DB スキーマ変更、API 破壊など) は issue / PR コメントで事前通知
