---
marp: true
theme: default
paginate: true
style: |
  section {
    font-family: 'Inter', 'Noto Sans JP', sans-serif;
    font-size: 22px;
    padding: 40px 60px;
    color: #1e293b;
    background-color: #ffffff;
  }
  h1 {
    color: #0f172a;
    font-size: 1.6em;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 8px;
    margin-bottom: 16px;
  }
  h2 {
    color: #334155;
    font-size: 1.2em;
  }
  h3 {
    color: #334155;
    font-size: 1.0em;
  }
  strong {
    color: #0f172a;
  }
  em {
    color: #64748b;
    font-style: normal;
  }
  code {
    background-color: #f1f5f9;
    color: #334155;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85em;
  }
  pre {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    font-size: 0.8em;
  }
  table {
    font-size: 0.78em;
    width: 100%;
  }
  th {
    background-color: #f1f5f9;
    color: #0f172a;
    font-weight: 600;
  }
  td {
    border-color: #e2e8f0;
  }
  blockquote {
    border-left: 3px solid #94a3b8;
    padding-left: 16px;
    color: #475569;
    font-size: 0.95em;
  }
  ul, ol {
    font-size: 0.95em;
  }
  a {
    color: #2563eb;
  }
  section::after {
    color: #94a3b8;
    font-size: 0.65em;
  }
---

<!-- _paginate: false -->

# オフィスにAIを住まわせたら家賃を請求された

**SOMS — Symbiotic Office Management System**

GPU 1台。Docker 12サービス。クラウド月額 $0。
建物まるごとAIの身体にする、ローカルLLM × IoT 実験。

---

# よくある「スマート」の実態

> 「スマートシティ」と名乗るシステムの多くは、建物の外に脳がある。

| やりたいこと | 現実 |
|---|---|
| リアルタイムAI制御 | クラウド往復で数百ms遅延。ネットワーク切れたら全停止 |
| データ駆動の意思決定 | 自治体が自分のデータをAPI経由で購入する構造 |
| 住民のプライバシー | カメラ映像の保管権限が外部ベンダーに帰属 |

脳が体の外にある生き物は——たぶん長生きできない。

**発想の転換**: データが生まれた建物の中で、全部処理すればいい。

---

# SOMS: 建物を一匹の生き物にする

GPU 1台のサーバーが「脳」。センサーとカメラが「感覚器官」。MQTTが「神経系」。

```
┌────────────────────────────────────────────────────────┐
│           人間インターフェース層                           │
│  Dashboard (React 19)  |  Voice (VOICEVOX)  |  Wallet  │
├────────────────────────────────────────────────────────┤
│  脳: LLM ReActループ (Think → Act → Observe, 最大5反復)  │
├────────────────────────────────────────────────────────┤
│  視覚: YOLOv11 物体検出 + 姿勢推定                       │
├────────────────────────────────────────────────────────┤
│  触覚: SensorSwarm (ESP32 Hub + Leaf, 4種トランスポート)  │
└────────────────────────────────────────────────────────┘
         全層が MQTT で疎結合。外部通信ゼロ。
```

30秒ごとに「考えて、動いて、観察する」。正常なら何もしない。異常を見つけたら——人間にお願いする。

---

# 30秒で起きること: CO2が上がった日

```
[T+0s]  ESP32: "CO2 1050ppm です"  → MQTT → WorldModel更新

[T+3s]  LLM: "高いな。3人いるし、換気しよう"
        → get_active_tasks() → 換気タスクなし
        → create_task("キッチンの換気", bounty=1500, urgency=3)

[T+5s]  Sanitizer: bounty ≤ 5000 ✓  urgency ∈ [0,4] ✓
        → ダッシュボードにカード表示
        → VOICEVOX: 「キッチンの換気をお願いします、1500ポイントです」

[T+??]  人間: 窓を開ける → 完了 → Wallet: 1500ポイント振替
```

AIは判断する。人間は動く。ちゃんと払う。
窓の開け方をAPIで教える必要はない。

---

# 技術スタック: 全部ローカル、全部オープン

| 役割 | 技術 | ひとこと |
|---|---|---|
| 脳 | Qwen2.5 14B + Ollama (ROCm) | 51 tok/s。応答3.3秒 |
| 視覚 | YOLOv11 (検出 + 姿勢推定) | 座りすぎ検知で健康アドバイス |
| 神経 | MQTT + MCP (JSON-RPC 2.0) | ESP32でもLLMのツール呼び出しに応答 |
| 触覚 | ESP32 SensorSwarm (Hub + Leaf) | WiFi不要のLeafはバッテリー駆動 |
| 声 | VOICEVOX | 拒否ストック100件事前生成。無視されると拗ねる |
| 経済 | 複式簿記 + デマレッジ + PWA | 貯めると減る。使うと増える |
| 基盤 | Docker Compose × 12 | GPU 1台、電源1本、クラウド $0 |

AMD RX 9700 (RDNA4) で全サービス稼働中。Phase 0、すでに動いている。

---

# AIがお金を配る経済圏

> 「窓を開けてください」——これはAPIコールでは解決できない。

LLMが状況を判断してタスクを作り、報酬を提示する。人間は自由意志で受けるか選ぶ。

| 仕組み | 設計意図 |
|---|---|
| タスク報酬 500〜5,000 pt | 難易度と緊急度でLLMが値付け |
| 複式簿記 (DEBIT + CREDIT) | ポイントにも帳簿の品格を |
| 送金手数料 5% → 焼却 | 流通するほど希少になる |
| デマレッジ 2%/日 | 貯金は毎日2%溶ける。使え |
| デバイスXP → 報酬乗数 1〜3倍 | センサーが長く働くほどゾーンが豊かに |

全自動ではなく**共生**。AIの知性と人間の身体性の分業。
——AIに体がないのは仕様であって、バグではない。

---

# 数字で見る Core Hub

| 指標 | 値 | 意味 |
|---|---|---|
| データ圧縮比 | **50,000 : 1** | 50GB/日の生データ → 外部送信は1MB |
| 映像保存時間 | **0秒** | YOLO推論後に即破棄。GDPRの最適解 |
| クラウド月額 | **$0** | ランニングコストはGPU 1台の電気代のみ |
| 応答レイテンシ | **3.3秒** | 正常時。ツール呼び出し込みでも6.6秒 |
| エッジノード展開 | **config.json 差し替え** | 同一ファームウェア、センサー構成だけ変更 |
| Hub横展開 | **システムプロンプト差し替え** | オフィス→農場→店舗。コード変更ゼロ |

50GBの生データから1MBの統計だけ外に出す。
Hub撤去 = 全データ消失。これが物理的なデータ主権。

---

# ヴィジョン: 1オフィスから都市へ

```
Phase 0 (現在)     1 Hub, 1部屋     ← 全機能E2E稼働中
Phase 1            1 Hub, 10+ノード   多ゾーン + Data Lake
Phase 2            2-3 Hub           Core Hub間連携 + City Data Hub
Phase 3            10+ Hub           都市展開。外部送信 0 bytes
```

各Hubが1時間平均のCO2値を送信するだけで、都市の人流が浮かび上がる。
住宅街(朝7時) → オフィス街(9時) → 商業施設(夕方) → 住宅街(夜)

**送信データ: 数バイト/Hub/時間。** プライバシーコストはゼロ。

システムプロンプトを差し替えるだけで、オフィス・農場・店舗・公共施設に展開できる。
建物に脳を置く。都市に知性が宿る。

---

<!-- _paginate: false -->

# オフィスにAIを住まわせたら、けっこう良い同居人だった

> GPU 1台。Docker 12サービス。クラウド $0。
> データは建物の外に出ない。AIは判断し、人間は動き、経済が回る。

Phase 0、動作中。コードは全部公開。

**GitHub**: `Office_as_AI_ToyBox`
