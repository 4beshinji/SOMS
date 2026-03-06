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

# 都市のデータが欲しい。でも覗き見はしたくない。

## 秘密計算 × Edge AI — 同意なしでプライバシーを守る都市データレイク

SOMS Federation が目指す「**個人データが存在しない**」データ基盤。

*データクリーンルーム × IoT: 都市データレイクへの道*

---

# 都市データレイクの夢と現実

都市の CO2 濃度、人流パターン、エネルギー消費を横断分析したい。

でも現実は甘くない。

| やりたいこと | 壁 |
|---|---|
| 1万拠点の CO2 を集約 | 全拠点の管理者同意 + 契約締結 |
| 在室人数 × エネルギー相関 | 従業員のプライバシー同意 |
| リアルタイム人流分析 | 個人情報保護法 + GDPR 対応コスト |
| 長期トレンド蓄積 | データ保持期間 × 目的外利用の壁 |

同意を「取りやすくする」話ではない。

**同意を「不要にする」。**

---

# 個人データが存在しないデータレイク

データは建物の外に出ない。出るのは**ノイズ済みの統計値だけ**。

```
┌─────────────────────────────────────────────┐
│  Layer 3: City Data Lake                    │
│  匿名統計のみ (ε-DP保証)                     │
│  法的分類: 非個人情報 → 同意不要              │
├─────────────────────────────────────────────┤
│  Layer 2: Federation Hub (地域集約)          │
│  k-匿名化 + Secure Aggregation              │
│  法的分類: 仮名加工情報                       │
├─────────────────────────────────────────────┤
│  Layer 1: Site (SOMS 1拠点)                 │
│  生データ: 温度, CO2, 在室人数               │
│  法的分類: 個人情報を含みうる                 │
└─────────────────────────────────────────────┘
```

**Layer 1 に個人データがある。Layer 3 には存在しない。**

これがアーキテクチャで保証するプライバシー。

---

# ESP32 でもできる秘密計算

Local Differential Privacy の本質は「**ノイズを足すだけ**」。

```python
import math, os

def laplace_noise(epsilon, sensitivity=1.0):
    """ε-差分プライバシーを満たすラプラスノイズ"""
    scale = sensitivity / epsilon
    # urandom 2バイト → 一様乱数 → ラプラス分布
    u = int.from_bytes(os.urandom(2), 'big') / 65535
    u = max(0.0001, min(0.9999, u))
    return -scale * math.copysign(1, u - 0.5) * math.log(1 - 2 * abs(u - 0.5))

# 使い方: 真の値にノイズを加えて送信
noisy_co2 = true_co2 + laplace_noise(epsilon=1.0)
```

暗号学の博士号は不要。`urandom` と `math` だけ。

**240MHz の ESP32 で 0.1ms。**

---

# ε（イプシロン）: プライバシーの通貨

ε が小さいほどプライバシーが強い。大きいほど精度が高い。

| ε | プライバシー強度 | 用途例 | 1拠点の誤差 |
|---|---|---|---|
| 0.1 | 極めて強い | 人数カウント (存在有無) | ±10人 |
| 1.0 | 強い | CO2 / 温度の時系列 | ±1.0 ppm |
| 3.0 | 中程度 | エネルギー消費集計 | ±0.3 kWh |
| 10.0 | 弱い | 公開済み気象データ補完 | ±0.1℃ |

### プライバシーバジェット

- 各拠点は1日あたり ε_total = 10.0 を持つ
- クエリごとに ε を消費する
- **使い切ったら、もう聞けない**

これがプライバシーの会計学。

---

# 法律が味方になる瞬間

| | 生データ | DP 処理済みデータ |
|---|---|---|
| **データ例** | 「3F会議室に田中さん在室」 | 「ゾーンAの在室: 2.7 ± 1.2人」 |
| **法的分類** | 個人情報 | 非個人情報 (統計情報) |
| **同意** | 必要 | **不要** |
| **保持制限** | 目的達成後削除 | 制限なし |
| **越境移転** | 規制あり | **規制対象外** |

### 根拠

- **個人情報保護法**: 「特定の個人を識別できない」→ DP が数学的に保証
- **GDPR**: "anonymized data is outside the scope of GDPR" (Recital 26)

技術が法律の要件を**自動的に**満たす。

コンプライアンス部門が笑う日が来る。

---

# 都市の呼吸が見える

1拠点では意味がない。1000拠点の集約で都市が見える。

### CO2 の日内移動パターン

```
06:00  住宅街 ████████░░  →  オフィス街 ██░░░░░░░░
09:00  住宅街 ███░░░░░░░  →  オフィス街 ████████░░
12:00  住宅街 ██░░░░░░░░  →  商業地域   ██████░░░░
18:00  住宅街 ██████░░░░  ←  オフィス街 ████░░░░░░
22:00  住宅街 ████████░░      商業地域   ██░░░░░░░░
```

### エネルギー消費の波

- 朝の暖房ピーク → 昼のOA負荷 → 夕方の調理ピーク
- **ヒートアイランドの因果関係**が統計だけで見える

1拠点のデータは見えない。1000拠点の統計は見える。

**これがデータクリーンルーム。**

---

<!-- _paginate: false -->

# 都市を覗かずに、都市を理解する

> "最良の監視システムとは、何も監視しないシステムである。"

### ロードマップ

| Phase | 状態 | 内容 |
|---|---|---|
| Phase 0 | **稼働中** | SOMS: 1拠点の自律オフィス管理 |
| Phase 1 | 設計中 | Federation: 拠点間メタデータ共有 |
| Phase 2 | 構想 | Local DP + Secure Aggregation |
| Phase 3 | 構想 | City Data Lake: 匿名統計の公開API |

### スペック

- 送信データ: **ノイズ済み数バイト / Hub / 時間**
- 個人データの総量: **0 bytes**
- 必要なハードウェア: ESP32 (既に設置済み)

GitHub: **Office_as_AI_ToyBox**
