# SOMS アクセスガイド (Access Guide)

このドキュメントは、SOMS（Symbiotic Office Management System）へのアクセス方法をまとめたものです。

## サービスエンドポイント一覧

> **注意**: `<SERVER_IP>` はサーバーの IP アドレスに置き換えてください（`hostname -I` で確認可能）。ローカルアクセスの場合は `localhost` を使用できます。

### サービスポート一覧

| サービス | ポート | コンテナ名 | 用途 |
|---------|--------|-----------|------|
| Dashboard Frontend (nginx) | 80 | soms-frontend | Web管理画面 (SPA) |
| Dashboard Backend API | 8000 | soms-backend | REST API ([Swagger UI](http://<SERVER_IP>:8000/docs)) |
| Mock LLM | 8001 | soms-mock-llm | 開発用LLMシミュレータ |
| Voice Service | 8002 | soms-voice | Text-to-Speech |
| Wallet Service | 127.0.0.1:8003 | soms-wallet | クレジット経済API (localhostのみ) |
| Wallet App (PWA) | 8004 (HTTPS: 8443) | soms-wallet-app | モバイルウォレット (HTTPS対応) |
| SwitchBot Bridge | 8005 | soms-switchbot | SwitchBot Cloud Webhook |
| Auth Service | 127.0.0.1:8006 | soms-auth | OAuth認証 + JWT発行 (localhostのみ) |
| PostgreSQL | 127.0.0.1:5432 | soms-postgres | データベース (localhostのみ) |
| VOICEVOX Engine | 50021 | soms-voicevox | 音声合成エンジン |
| Ollama (LLM) | 11434 | soms-ollama | ローカルLLM (OpenAI互換API) |
| MQTT Broker | 1883 (TCP) / 9001 (WS) | soms-mqtt | IoTメッセージング |

### MQTT 接続

- **プロトコル**: MQTT v3.1.1
- **TCP**: `mqtt://<SERVER_IP>:1883`
- **WebSocket**: `ws://<SERVER_IP>:9001`
- **認証**: ユーザー名 `soms` / パスワード `soms_dev_mqtt`

## ファイアウォール設定

外部からアクセスする場合、以下のポートを開放してください：

```bash
sudo ufw allow 80/tcp      # Dashboard
sudo ufw allow 8000/tcp    # Backend API
sudo ufw allow 8004/tcp    # Wallet App
sudo ufw allow 11434/tcp   # Ollama LLM
sudo ufw allow 1883/tcp    # MQTT (TCP)
sudo ufw allow 9001/tcp    # MQTT (WebSocket)
```

> **セキュリティ注意**: PostgreSQL (5432)、Wallet Service (8003)、Auth Service (8006) は意図的に `127.0.0.1` にバインドされています。外部公開しないでください。

## セキュリティに関する注意

- 現在の設定では、すべてのサービスがHTTP（非暗号化）です
- 本番環境では以下を推奨します：
  - HTTPS/TLS の設定
  - 認証・認可機構の実装
  - ファイアウォールによるアクセス制限
  - VPN経由でのアクセス

## トラブルシューティング

### サービスに接続できない

1. サービスが起動しているか確認：
   ```bash
   docker compose -f infra/docker-compose.yml ps
   ```

2. ファイアウォールの状態を確認：
   ```bash
   sudo ufw status
   ```

3. サーバーのIPアドレスを確認：
   ```bash
   hostname -I
   ```

### サービスを再起動する

```bash
docker compose -f infra/docker-compose.yml restart
```

---

**更新日**: 2026-02-21
