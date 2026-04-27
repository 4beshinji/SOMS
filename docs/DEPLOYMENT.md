# SOMS デプロイメントガイド (Deployment Guide JA)

## 1. 前提条件

ターゲットマシンに以下がインストールされていることを確認してください。

-   **OS**: Linux (Ubuntu 22.04+ 推奨)
-   **Git**: `sudo apt install git`
-   **Docker Engine**: [インストールガイド](https://docs.docker.com/engine/install/ubuntu/)
-   **Docker Compose Plugin**: `sudo apt install docker-compose-plugin`
    -   `docker compose version` で動作を確認してください。
-   **AMD Drivers (ROCm)**: ローカルLLMを使用する場合にのみ必要です。[インストールガイド](https://rocm.docs.amd.com/en/latest/deploy/linux/quick_start.html)。
    -   `rocminfo` または `clinfo` コマンドで動作を確認してください。

## 2. クローンとセットアップ

1.  **リポジトリの複製**:
    ```bash
    git clone <repository_url> Office_as_AI_ToyBox
    cd Office_as_AI_ToyBox
    ```

2.  **環境設定**:
    ```bash
    cp env.example .env
    # 必要に応じて .env を編集 (LLM接続先、PostgreSQL認証情報等)
    nano .env
    ```

3.  **初期化 (ボリュームとネットワーク作成)**:
    ```bash
    chmod +x infra/scripts/setup_dev.sh
    ./infra/scripts/setup_dev.sh
    ```

## 3. 利用シナリオの実行

### シナリオ A: 完全シミュレーション (ハードウェア不要・GPU不要)

ロジックやネットワークフローの検証に最適です。Mock LLM + 仮想エッジデバイスで動作します。

```bash
./infra/scripts/start_virtual_edge.sh
```

起動サービス: Brain, Dashboard (Backend+Frontend), Mock LLM, Voice Service, VOICEVOX, Wallet, PostgreSQL, Mosquitto, Virtual Edge, Virtual Camera

-   **検証方法**: `python3 infra/tests/e2e/e2e_full_test.py` でE2Eテスト (7シナリオ) を実行

### シナリオ B: 実機本番環境 (AMD ROCm GPU + エッジデバイス)

1.  **`.env` の編集**:
    -   `LLM_API_URL=http://llm:8080/v1` (Docker内部通信。`llm` サービスのコンテナ内ポートは 8080、ホスト公開ポートは 11434)
    -   `LLM_MODEL=qwen3.5:9b` (クライアント識別用の文字列。実体は `LLM_MODEL_FILE` で選択)
    -   `LLM_MODEL_FILE=qwen3.5-9b-q4km.gguf` (起動時に `--model /models/<file>` で読み込まれる GGUF ファイル名。14B 版を使う場合はそのファイルを指定)
    -   `LLM_MODEL_PATH=./llm/models` (GGUF を配置するホスト側ディレクトリ。コンテナの `/models:ro` にマウントされる)
    -   `RTSP_URL` を実際のカメラのIPアドレスに設定
    -   PostgreSQL認証情報を本番用に変更

2.  **GPU デバイスの確認**:
    -   `docker-compose.yml` 内の `llm` / `perception` サービスの `devices` マッピングを確認:
      ```yaml
      devices:
        - /dev/kfd:/dev/kfd
        - /dev/dri/card1:/dev/dri/card1        # dGPU
        - /dev/dri/renderD128:/dev/dri/renderD128
      ```
    -   **重要**: `/dev/dri` 全体を渡すとiGPUリセット→GNOMEクラッシュの原因になります。dGPU のみを指定してください。

3.  **GGUF モデルの準備**:
    ```bash
    # GGUF を ${LLM_MODEL_PATH:-./llm/models} 配下に配置する
    # (コンテナ起動時に --model /models/<file>.gguf で読み込まれる)
    mkdir -p infra/llm/models
    # 例: Hugging Face からダウンロード (huggingface-cli を使う場合)
    huggingface-cli download Qwen/Qwen2.5-9B-Instruct-GGUF \
      qwen3.5-9b-q4km.gguf --local-dir infra/llm/models
    # またはブラウザで直接ダウンロードして infra/llm/models/ に置く
    ```
    > 注: `ollama pull` は不要です。llama.cpp サーバーは起動時にファイルを直接読み込みます。

4.  **全サービスの起動**:
    ```bash
    docker compose -f infra/docker-compose.yml up -d --build
    ```
    起動後、`curl http://localhost:11434/health` で llama.cpp サーバーの稼働を確認できます。

### シナリオ C: ホストで llama-server を直接起動 (Docker外でLLM実行)

GPU トラブルシュートやモデル切り替えを高速に行いたい場合、`llama-server` をホスト OS で直接起動し Docker 内のサービスから接続できます:

```bash
# ホスト側で llama-server を起動 (ROCm ビルド)
llama-server --model /path/to/qwen3.5-9b-q4km.gguf \
  --host 0.0.0.0 --port 11434 \
  --n-gpu-layers 99 --ctx-size 32768 \
  --parallel 4 --cont-batching --flash-attn on

# .env を編集
LLM_API_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen3.5:9b
```

`docker-compose.yml` の `brain` / `voice-service` に `extra_hosts: host.docker.internal:host-gateway` が設定済みです。この場合、Docker Compose 側の `llm` サービスは起動不要です (`docker compose up` 時に該当サービスを除外してください)。

## 4. サービスの確認

```bash
# 全コンテナの状態確認
docker compose -f infra/docker-compose.yml ps

# ログ確認
docker logs -f soms-brain        # Brain の認知ループ
docker logs -f soms-voice        # 音声合成
docker logs -f soms-backend      # Dashboard API

# ダッシュボード
# ブラウザで http://localhost にアクセス

# API ドキュメント (Swagger UI)
# Backend:  http://localhost:8000/docs
# Wallet:   http://localhost:8003/docs
# Voice:    http://localhost:8002/docs
```

## 5. サービス一覧

| サービス | ポート | コンテナ名 | 用途 |
|---------|--------|-----------|------|
| Dashboard Frontend | 80 | soms-frontend | nginx (SPA + リバースプロキシ) |
| Dashboard Backend | 8000 | soms-backend | タスクCRUD API |
| Mock LLM | 8001 | soms-mock-llm | テスト用LLMシミュレータ |
| Voice Service | 8002 | soms-voice | 音声合成 + LLMテキスト生成 |
| SwitchBot Bridge | 8005 | soms-switchbot | SwitchBot Cloud Webhook |
| Auth Service | 127.0.0.1:8006 | soms-auth | OAuth認証 (Slack + GitHub) |
| PostgreSQL | 127.0.0.1:5432 | soms-postgres | Dashboard/Auth 共有DB |
| VOICEVOX | 50021 | soms-voicevox | 日本語音声合成エンジン |
| llama.cpp Server | 11434 (host) → 8080 (container) | soms-llm | LLM推論 (llama.cpp + ROCm) |
| MQTT | 1883 | soms-mqtt | メッセージブローカー |
| Perception | host network | soms-perception | YOLOv11 画像認識 + MTMC追跡 |

## 6. トラブルシューティング

-   **MQTT Connection Refused**: `docker ps` で `soms-mqtt` が起動しているか確認。
-   **LLM Out of Memory**: `rocm-smi` でVRAM使用量を確認。より小さい量子化 (Q4_K_S や Q3_K_M) の GGUF を `infra/llm/models/` に配置し、`LLM_MODEL_FILE` で切り替えてください。
-   **Permission Denied**: ユーザーが `docker` および `video`/`render` グループに追加されているか確認: `sudo usermod -aG docker,video,render $USER`
-   **iGPU クラッシュ**: `/dev/dri` 全体ではなく dGPU デバイスのみを `devices:` に指定してください。
-   **PostgreSQL 接続エラー**: `docker logs soms-postgres` でログを確認。`.env` の `POSTGRES_USER`/`POSTGRES_PASSWORD` がdocker-compose.ymlの設定と一致しているか確認。
