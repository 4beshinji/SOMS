# SOMS — 自己増殖する都市知能

**分散型ローカル LLM による自律的空間管理ネットワーク**

---

## 0. この文書の位置づけ

```
本文書 (CITY_SCALE_VISION.md)     ← ビジョン・自己拡張メカニズム・都市展開
  ├── docs/architecture/adr-privacy-preserving-federation.md
  │                                ← プライバシー保護型データ集約
  ├── docs/architecture/adr-federation.md
  │                                ← Federation 基盤設計
  └── docs/SYSTEM_OVERVIEW.md     ← 技術的全体像
        └── CLAUDE.md             ← 開発者向けリファレンス
```

---

## 1. 問題: なぜ都市は情報化されていないのか

現代の「スマートシティ」は根本的矛盾を抱えている:

| 表向きの主張 | 実態 |
|-------------|------|
| 「データ駆動の都市経営」 | センサーデータはクラウドベンダーに吸い上げられ、都市は自身のデータにアクセスするためにAPI料金を支払う |
| 「AIによる最適化」 | 中央集権的な推論サーバーが全データを処理し、ネットワーク障害で全機能が停止 |
| 「市民のための技術」 | カメラ映像は外部企業のクラウドに保存され、プライバシー主権は都市にない |
| 「リアルタイム分析」 | クラウド往復で数百ms〜秒の遅延、真のリアルタイムではない |

**核心**: データが生成される場所（都市）と処理される場所（クラウド）が分離している。

## 2. SOMSの回答: 自律分散知能 (v2 B2B)

> **空間が自身のデータを、自身の計算資源で、自身の論理で処理する。**
> **どんなセンサーでも追加すれば即座に統合され、LLM の判断に組み込まれる。**

SOMSは単なるセンサーネットワークではない。**自動統合される観測網**である。

### 2.1 自動統合サイクル (v2)

```
[1] センサーを設置 (ESP32、SwitchBot、Zigbee、カメラ)
         │
[2] MQTT に `{"value": X}` を publish
         │
[3] WorldModel が即座に認識、DeviceRegistry に追加
         │
[4] CoreHub の LLM がデータを解釈し、必要に応じてタスクを dispatch
         │
[5] 人間がタスクを受諾→完了、task_audit_log に記録
         │
[6] データ蓄積 → LLMの判断精度向上 → [1] に戻る
```

v1 にあった経済インセンティブループ (bounty / device XP / zone multiplier /
demurrage / device staking) は v2 で削除された (労働法・資金決済法の制約)。
詳細: `docs/architecture/v2-b2b-migration.md`。

v2 の参加フレームは B2B — 導入企業の従業員が利用者であり、インセンティブ
設計は企業側のオペレーション範疇に任せる。技術的な自動統合 (センサー
発見、LLM による監視、タスク自動生成、監査証跡) がコアバリュー。

### 2.2 参加者の役割

| 参加者 | できること | 技術的な効果 |
|--------|-----------|------------|
| **オペレータ** | ESP32/SwitchBot/Zigbee を設置 | センサー密度が上がり WorldModel の精度が向上 |
| **運用チーム** | CoreHub を運用 | GPU + ローカル LLM で推論 |
| **従業員** | 管理者が割当てたタスクを遂行 | 物理空間が維持される。完了は `task_audit_log` に記録 |
| **管理者** | タスクの優先度・割当先 (`skill_level`) を決める | 公式な業務オペレーション |

### 2.3 自動センサー検出

CoreHubは新しいセンサーを待たない。自分から探しに行く:

1. **TCP ポートスキャン** — ネットワーク上の新デバイスを自動検出
2. **URL プローブ** — RTSP/HTTP カメラのエンドポイントを探索
3. **YOLO 検証** — カメラ映像に対して推論を実行し、有用なフィードかを判定
4. **MQTT 自動統合** — `{"value": X}` を送信する任意のデバイスを即座にWorldModelに組み込み

センサーを電源に繋ぐだけで、CoreHubが見つけて、理解して、活用する。

---

## 3. アーキテクチャ: 3層データ処理

```
Layer 0: 物理世界 (Raw Signal)
  │  センサー電圧値、カメラRGBピクセル、音声波形
  │  → 量が膨大、意味不明、保存不要
  ▼
Layer 1: CoreHub (Local Intelligence)
  │  ローカルLLMがリアルタイム解釈
  │  センサーフュージョン、YOLO推論、イベント検出
  │  → この層でデータの 99% は破棄される (意味だけ抽出)
  ▼
Layer 2: City Data Hub (Aggregation)
  │  複数CoreHubの構造化データを集約
  │  時空間分析、パターン抽出、都市規模の最適化
  ▼
Layer 3: 洞察と行動
     都市計画への入力、政策提言、資源配分最適化
```

**圧縮比**: 生信号 50GB/日 → 外部送信 1MB = **50,000:1**

### 3.1 データ主権の原則

| 原則 | 実装 |
|------|------|
| **生データは外に出ない** | 全Layer 0データはCoreHub内で処理・破棄。映像はRAM上のみ |
| **推論はローカルで完結** | 各CoreHubが独自のLLMを持ち、自律判断可能 |
| **集約は構造化データのみ** | City Data Hubに送られるのは統計値・イベント・判断ログのみ |
| **ネットワーク切断耐性** | 各CoreHubは孤立状態でも独立動作を継続 |
| **物理的削除権** | CoreHubを撤去すれば、その全生データが物理的に消失 |

### 3.2 CoreHub内部データフロー

```
┌──────────────────────────────────────────────────────────────┐
│                        CoreHub 内部                           │
│                                                              │
│  [Sensor Nodes] ──→ [MQTT Broker] ──→ [WorldModel]         │
│                                         │                    │
│                           ┌─────────────┤                    │
│                           ▼             ▼                    │
│                    [Event Store]   [LLM Brain]               │
│                    (時系列DB)      (ReAct Loop)              │
│                           │             │                    │
│                           ▼             ▼                    │
│                    [Data Lake]    [Action Log]               │
│                    (生イベント)   (判断+根拠)                │
│                           │             │                    │
│                           └──────┬──────┘                    │
│                                  ▼                           │
│                           [Data Mart]                        │
│                           (集約済み)                         │
└──────────────────────────┬───────────────────────────────────┘
                           │ 構造化データのみ (~1MB/日)
                           ▼
                    [City Data Hub]
```

---

## 4. CoreHub: 自律知能ノード

### 4.1 コンポーネント

| コンポーネント | 機能 | 実装済み |
|--------------|------|---------|
| Local Intelligence Engine | ローカルLLMによるReAct認知ループ (30秒サイクル, 5イテレーション) | `services/brain/` |
| State Aggregator | センサーフュージョン + 状態管理 (WorldModel) | `services/brain/src/world_model/` |
| Vision Processor | YOLOv11 物体検出・姿勢推定・転倒検知・MTMC追跡 | `services/perception/` |
| Message Bus | MQTT (MCP over JSON-RPC 2.0) | Mosquitto |
| Audit Trail | タスクライフサイクル監査ログ (金額なし) | `task_audit_log` in dashboard DB |
| Human Interface | ダッシュボード + 音声合成 + モバイルウォレット | `services/dashboard/`, `services/voice/` |
| Safety Layer | 入力検証 + 憲法的AI (行動制約) | `services/brain/src/sanitizer.py` |
| Auto-Discovery | センサー・カメラ自動検出 | `services/perception/src/camera_discovery.py` |

### 4.2 ハードウェア要件

| 構成要素 | 最小構成 | 推奨構成 |
|---------|---------|---------|
| GPU | 16GB VRAM (量子化LLM) | 32GB VRAM (フル推論 + Vision) |
| CPU | 8コア | 16コア |
| RAM | 32GB | 64GB |
| Storage | 500GB SSD | 2TB NVMe |
| Network | 1GbE + WiFi AP | 2.5GbE + 専用IoT WiFi |
| 消費電力 | 150W (idle) ~ 350W (推論時) | |
| 設置面積 | A4用紙程度 (Mini PC) | ラックマウント 1U |

### 4.3 センサーノード

| ノード種別 | ハードウェア | 通信 | 電源 |
|-----------|------------|------|------|
| 環境センサー | ESP32 + BME680 + MH-Z19C | WiFi / BLE Mesh | USB / バッテリー |
| カメラノード | ESP32 WROVER / Pi Zero | WiFi | USB / PoE |
| 音響センサー | ESP32 + I2S MEMS マイク | WiFi | USB |
| 振動センサー | ESP32 + ADXL345 | WiFi / LoRa | ソーラー + バッテリー |
| 屋外環境 | ESP32 + IP67筐体 | LoRa / WiFi | ソーラー + バッテリー |
| SwitchBot | 市販スマートデバイス9種 | クラウドAPI経由MQTT統合 | 各デバイス依存 |

**共通プロトコル**: MCP over MQTT (JSON-RPC 2.0)。どんなデバイスでも `{"value": X}` をMQTTに送れば参加できる。

---

## 5. City Data Hub: 都市規模の知能

City Data Hubは **CoreHubの集約点** であり、自身は生データを処理しない。

```
              ┌─────────────────────────────────────────────┐
              │              City Data Hub                    │
              │                                              │
              │  Data Warehouse  │  Analytics  │  Dashboard  │
              │  (全Hub統合)     │  (時空間)   │  (俯瞰)     │
              │                                              │
              │  入力: 各CoreHub の Data Mart (1MB/Hub/日)   │
              │  出力: 都市レポート、異常パターン、資源配分    │
              └─────────────────────────────────────────────┘
```

### City Data Hubが解く問い

| 問い | データソース |
|------|------------|
| 「A地区とB地区で同時にCO2が上昇 — 広域の大気汚染か？」 | 複数HubのData Mart |
| 「通勤パターンの変化を検出」 | 複数Hubの在室データ |
| 「Hub-03のセンサー精度が劣化 — メンテナンス必要」 | Hubヘルスメトリクス |
| 「新しい拠点の最適なセンサー配置は？」 | 既存Hubの有効性データ |
| 「どのゾーンにセンサーを追加すれば最も異常検知精度が向上するか？」 | タスク完了率・センサーカバレッジ |

### Hub間通信

```
CoreHub ──── MQTT (QoS 1) or HTTPS ────→ City Data Hub
                 │
                 │  ペイロード: Data Mart JSON
                 │  頻度: 1時間ごと
                 │  認証: mTLS (相互TLS)
                 │  ネットワーク障害時: ローカルキューに蓄積、復旧後一括送信
                 │  CoreHubの自律動作は常に継続
```

---

## 6. 領域特化

CoreHubのソフトウェアは共通。接続するセンサーとシステムプロンプト（憲法）を変えることで、あらゆる空間に適用できる:

| Hub種別 | センサー構成 | LLMの専門知識 | タスク例 |
|---------|------------|--------------|---------|
| **都市環境** | 気象, 大気質, 騒音, カメラ | 安全管理, 環境モニタリング | 警報, 点検, 修繕 |
| **オフィス** | 温湿度, CO2, カメラ | 快適性, 健康, 生産性 | 換気, 清掃, 備品補充 |
| **農業** | pH, EC, 水温, 照度 | 水耕栽培, 作物管理 | 養液調整, 収穫 |
| **店舗** | 人流カメラ, 温湿度 | 顧客行動, 在庫管理 | 品出し, 陳列変更 |
| **住宅** | 環境, セキュリティカメラ | 居住者ケア, エネルギー | 見守り, 節電 |

全Hubが同じMQTTプロトコルとData Martスキーマを共有するため、City Data Hubは **異種Hubのデータを統一的に集約** できる。

関連プロジェクト:
- **[auto_JA](../auto_JA/)** — IoT農業・養殖管理
- **[HEMS](../hems/)** — 独居者向けパーソナルAI + スマートホーム

---

## 7. 展開ロードマップ

### Stage 1: 単一CoreHub (現在)

単一ノードの全機能実証。

**達成済み**:
- [x] Brain ReActループ (6ツール, 最大5反復)
- [x] WorldModel + センサーフュージョン
- [x] MCP over MQTT (JSON-RPC 2.0)
- [x] エッジデバイス (MicroPython + C++ 両対応)
- [x] Perception (YOLOv11: 物体検出, 姿勢推定, 4層活動分析, 転倒検知, MTMC追跡)
- [x] task_audit_log + Admin Activity タブ (v2)
- [x] Dashboard (React 19) + Admin Console + Voice (VOICEVOX)
- [x] OAuth認証 (Slack / GitHub + JWT)
- [x] SwitchBot連携 (9デバイス種) + Zigbee2MQTT ブリッジ
- [x] SensorSwarm Hub+Leaf ネットワーク
- [x] 仮想テスト環境 (Mock LLM + Virtual Edge + Virtual Camera)
- [x] 1,071 ユニットテスト (7サービス)

**次のステップ**:
- [ ] Data Lake / Data Mart パイプライン
- [ ] 本番LLM (llama.cpp + Qwen3.5) 24時間連続稼働
- [ ] センサーノード量産 (統一ファームウェア, config.json差し替え)

### Stage 2: 複数CoreHub + City Data Hub

2台目のCoreHubを設置し、Hub間連携を実証。

- Hub間通信プロトコル (mTLS)
- Data Martスキーマの標準化
- ネットワーク分断時の自律動作検証 (72時間孤立テスト)
- ゼロタッチプロビジョニング (設置→自動設定→稼働)

### Stage 3: 都市展開 — N CoreHub

- District Data Hub (地区集約) の中間層
- センサーノード大量デプロイ (OTA更新)
- 都市規模の時空間分析エンジン
- 公開データとの統合 (気象, 交通, 大気質)

### Stage 4: 自己進化

- LLMがシステムコードを理解し、新センサータイプへの対応コードを自動生成
- 新イベントパターンの自動検出と新規ルール提案
- CoreHub間での知識共有 (A拠点で学んだパターンをB拠点に展開)
- タスク成功/失敗パターンからの最適依頼方法の学習

---

## 8. 誰でもCoreHubを立てられる

SOMSはオープンソースであり、特別な許可なく誰でも自分のCoreHubを運用できる。

### 最小構成 (シミュレーション)

```bash
# Docker さえあれば動く (GPUなし)
git clone <repository_url> && cd Office_as_AI_ToyBox
cp env.example .env
./infra/scripts/start_virtual_edge.sh
```

### 本番構成

```bash
# AMD ROCm GPU + 実センサー
docker compose -f infra/docker-compose.yml up -d --build
```

### センサーだけ追加

既存のCoreHubにセンサーを追加するだけでも参加できる:

```bash
# ESP32, Raspberry Pi, PC, 何からでも
mosquitto_pub -h <hub_ip> -t 'office/my_zone/sensor/my_device/temperature' \
  -m '{"value": 23.5}'
```

CoreHubが自動認識し、WorldModel + DeviceRegistry に登録される。LLM の判断材料に即座に組み込まれる。

---

## 付録 A: 用語定義

| 用語 | 定義 |
|------|------|
| **CoreHub** | ローカルLLM + GPUを持つ自律知能ノード。1台で完全に独立動作 |
| **Sensor Node** | CoreHubに接続される末端デバイス (ESP32等)。計算能力は最小限 |
| **City Data Hub** | 複数CoreHubの集約データを統合分析するサーバー (構想段階) |
| **Data Mart** | 集約・要約された分析用データ。Hub外への唯一の送信対象 |
| **MCP over MQTT** | AIツール呼び出し (JSON-RPC 2.0) をMQTT上で実装したプロトコル |
| **ReAct Loop** | Think → Act → Observe の認知サイクル |
| **task_audit_log** | タスクライフサイクルの追記専用証跡 (金額なし、コンプライアンス用途) |
| **DeviceRegistry** | Brain in-memory のデバイス状態追跡。`GET /devices/status` で公開 |

## 付録 B: 関連文書

| 文書 | 内容 |
|------|------|
| `docs/SYSTEM_OVERVIEW.md` | 技術的全体像 |
| `docs/architecture/v2-b2b-migration.md` | v1→v2 移行詳細 (経済システム削除の経緯) |
| `docs/architecture/adr-federation.md` | 多拠点フェデレーション設計 (v2) |
| `docs/CONTRIBUTING.md` | 参加ガイド |
| `docs/architecture/detailed_design/` | 各サブシステムの詳細設計 |
| `CLAUDE.md` | 開発者向けリファレンス |
