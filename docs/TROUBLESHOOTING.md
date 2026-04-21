# トラブルシューティングガイド

## 目次

1. [Docker / 起動問題](#1-docker--起動問題)
2. [MQTT 接続問題](#2-mqtt-接続問題)
3. [PostgreSQL 問題](#3-postgresql-問題)
4. [LLM / Brain 問題](#4-llm--brain-問題)
5. [センサー / MQTT データ問題](#5-センサー--mqtt-データ問題)
6. [フロントエンド問題](#6-フロントエンド問題)
7. [GPU / ROCm 問題](#7-gpu--rocm-問題)
8. [テスト実行問題](#8-テスト実行問題)

---

## 1. Docker / 起動問題

### コンテナが起動しない

```bash
# 全コンテナのステータス確認
docker compose -f infra/docker-compose.yml ps

# 問題コンテナのログを確認
docker logs soms-brain
docker logs soms-backend
docker logs soms-postgres
```

### ポートが既に使用されている

症状: `bind: address already in use`

```bash
# 使用中のポートを特定
sudo lsof -i :5432   # PostgreSQL
sudo lsof -i :1883   # MQTT
sudo lsof -i :8000   # Backend

# 既知の競合: langflow-postgres が 5432 を占有している場合
docker stop langflow-postgres
```

ポート競合の自動検出:
```bash
./infra/scripts/start_virtual_edge.sh  # 起動前にポートチェックを実行
```

### Docker 権限エラー

症状: `permission denied while trying to connect to the Docker daemon`

```bash
# docker グループに追加されているか確認
groups $USER

# 追加されていない場合 (要 sudo パスワード)
sudo usermod -aG docker $USER

# 現セッションで有効化 (再ログイン不要)
newgrp docker
```

### コンテナ内のソースコードが反映されない

Brain/Backend/Voice は bind mount (`volumes: - ../services/X/src:/app`) なので、
ファイル変更後にコンテナ再起動するだけで反映される:

```bash
docker compose -f infra/docker-compose.yml restart brain
docker compose -f infra/docker-compose.yml restart backend
```

---

## 2. MQTT 接続問題

### MQTT に接続できない

```bash
# MQTT ブローカーのログ確認
docker logs soms-mqtt

# 接続テスト (mosquitto_sub が必要)
mosquitto_sub -h localhost -p 1883 -u soms -P soms_dev_mqtt -t 'office/#' -v
```

### Brain が MQTT に接続できない

Brain の MQTT 接続は起動時に1回のみ試みる。失敗するとプロセスが終了する。
mosquitto が先に起動していることを確認:

```bash
# 起動順序確認
docker compose -f infra/docker-compose.yml ps mosquitto
# running でない場合
docker compose -f infra/docker-compose.yml up -d mosquitto
# 30秒待ってから Brain 起動
docker compose -f infra/docker-compose.yml up -d brain
```

### MQTT 認証エラー

デフォルト認証情報: `soms` / `soms_dev_mqtt`

`infra/.env` に以下が設定されているか確認:
```
MQTT_USER=soms
MQTT_PASS=soms_dev_mqtt
```

---

## 3. PostgreSQL 問題

### soms-postgres が起動しない (ポート競合)

```bash
# langflow などの他の PG コンテナを停止
docker stop langflow-postgres

# または env.ports でポートを変更
# infra/.env.ports で POSTGRES_PORT=5433 などに変更
```

### データベースが存在しない

```bash
# 初回セットアップ (volume 作成 + テーブル作成)
./infra/scripts/setup_dev.sh

# または手動でマイグレーション実行
docker exec soms-backend python -c "from database import create_tables; import asyncio; asyncio.run(create_tables())"
```

### `events` スキーマが存在しない

Brain サービスが起動時に `events` スキーマを自動作成する。
Brain が起動した後に Backend を起動すると解消される場合がある。

```bash
docker compose -f infra/docker-compose.yml restart brain
```

---

## 4. LLM / Brain 問題

### Brain が Tool call を実行しない

**Mock LLM を使用しているか確認:**

```bash
# Mock LLM のログ確認
docker logs soms-mock-llm

# Brain の LLM URL 確認
docker exec soms-brain env | grep LLM_API_URL
# 期待値: http://mock-llm:8000/v1 (開発環境)
#          http://ollama:11434/v1  (Ollama 使用時)
```

**Mock LLM のキーワードマッチ確認:**

Mock LLM はキーワードベースで Tool call を生成する。
温度・CO2・供給品のキーワードが含まれるプロンプトに反応する。
センサーデータが worldmodel に届いているか確認:

```bash
# MQTT にセンサーデータを手動パブリッシュ (テスト)
mosquitto_pub -h localhost -p 1883 -u soms -P soms_dev_mqtt \
  -t 'office/main/sensor/env_01/temperature' -m '{"value": 28.5}'
```

### Ollama に切り替える

```bash
# infra/.env を編集
LLM_API_URL=http://ollama:11434/v1
LLM_MODEL=qwen2.5:14b

# Ollama サービスを起動
docker compose -f infra/docker-compose.yml up -d ollama

# モデルをプル (初回のみ)
docker exec soms-ollama ollama pull qwen2.5:14b
```

### Brain が重複タスクを作成し続ける (既知の問題 L-9)

レート制限 (10タスク/時) に達した後も `get_active_tasks` チェックが不十分で重複が発生する場合がある。
一時的な対処: アクティブタスクを手動で完了させてクリア。

---

## 5. センサー / MQTT データ問題

### ダッシュボードにセンサーデータが表示されない

```bash
# 1. MQTT にデータが届いているか確認
mosquitto_sub -h localhost -p 1883 -u soms -P soms_dev_mqtt -t 'office/#' -v

# 2. イベントストアに書き込まれているか確認
docker exec soms-postgres psql -U soms -d soms -c \
  "SELECT zone, channel, value, timestamp FROM events.raw_events ORDER BY timestamp DESC LIMIT 10;"

# 3. Virtual Edge で仮想センサーデータを送信
docker compose -f infra/docker-compose.edge-mock.yml up -d virtual-edge
```

### SwitchBot デバイスが反応しない

```bash
# SwitchBot Bridge のログ確認
docker logs soms-switchbot

# 環境変数確認
docker exec soms-switchbot env | grep SWITCHBOT
# SWITCHBOT_TOKEN と SWITCHBOT_SECRET が設定されているか確認
```

---

## 6. フロントエンド問題

### ダッシュボードが表示されない (502 Bad Gateway)

nginx は Backend/Voice/Wallet サービスが起動していなくても起動する (lazy DNS resolution)。
502 は上流サービスが応答しないことを示す。

```bash
docker logs soms-frontend
docker logs soms-backend  # エラーの原因を確認
```

### 床面図にゾーンが表示されない

`config/spatial.yaml` が存在しかつ正しいフォーマットか確認:

```bash
# API から直接確認
curl http://localhost:8000/sensors/spatial/config | python3 -m json.tool | head -50
```

### フロントエンドのローカル開発で API エラー

```bash
cd services/dashboard/frontend
pnpm run dev
# Vite dev server は http://localhost:5173 で起動
# API プロキシは vite.config.ts で設定 (存在する場合)
# または直接 http://localhost:8000 のバックエンドに向ける
```

---

## 7. GPU / ROCm 問題

### Ollama が GPU を認識しない

```bash
# ROCm インストール確認
rocm-smi

# 環境変数設定 (RDNA4 の場合)
export HSA_OVERRIDE_GFX_VERSION=12.0.1

# infra/.env に追加
HSA_OVERRIDE_GFX_VERSION=12.0.1
```

### Perception サービスが GPU を使わない

Perception はホストネットワーキングを使用する。
GPU アクセスには `docker-compose.yml` の `devices:` セクションが必要。

```bash
docker logs soms-perception | grep -i "cuda\|rocm\|cpu"
```

---

## 8. テスト実行問題

### `python3 infra/tests/...` が ImportError を出す

プロジェクトの仮想環境を使用すること:

```bash
# 仮想環境でテスト実行
.venv/bin/python infra/tests/integration/test_sensor_api.py

# 仮想環境が存在しない場合
uv venv .venv
uv pip install -r infra/requirements-test.txt --python .venv/bin/python
```

### ポート設定エラー (テスト実行時)

```bash
# ポート環境変数を設定してからテスト実行
set -a && source infra/.env.ports && set +a
.venv/bin/python infra/tests/integration/test_sensor_api.py
```

---

## ログ一覧

| コンテナ | コマンド | 主な確認内容 |
|---------|---------|------------|
| Brain | `docker logs -f soms-brain` | ReAct サイクル、LLM ツール呼び出し |
| Backend | `docker logs -f soms-backend` | API エラー、DB 接続 |
| Voice | `docker logs -f soms-voice` | 音声合成エラー |
| Perception | `docker logs -f soms-perception` | カメラ検出、YOLO エラー |
| MQTT | `docker logs -f soms-mqtt` | 接続・認証エラー |
| PostgreSQL | `docker logs -f soms-postgres` | DB エラー |
| Mock LLM | `docker logs -f soms-mock-llm` | リクエスト受信ログ |
