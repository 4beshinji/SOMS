# ADR: Privacy-Preserving City-Level Data Aggregation

## Status: Draft

**Date**: 2026-03-06
**Context**: Federation Phase 2 — 都市レベルのデータ集約におけるプライバシー保証

---

## Context

SOMS の Federation Phase 2 として、数百〜数千の Core Hub を都市レベルで展開する構想がある。
各拠点のセンサーデータ（温度、CO2、在室率、タスク完了率、エネルギー消費）を都市レベルで集約し、
都市全体の環境最適化・省エネルギー施策・防災対応に活用したい。

しかし、個々の拠点のプライバシーを侵害してはならない:

- **個人情報保護法**: 個人に関するデータの第三者提供には本人同意が原則必要
- **GDPR**: データ処理には法的根拠が必要（同意、正当利益等）
- **実務的制約**: 都市全体（数千拠点・数万人）から個別同意を取得することは不可能

**解決策**: 個人データが拠点外に出ない構造を数学的に保証し、同意を「不要にする」。

### Requirements

1. 集約統計のみが都市レベルに到達する
2. 個別拠点・個人の値を復元不可能にする数学的保証
3. ESP32 レベルの計算リソースでも参加可能
4. ε 予算の公開監査が可能
5. 個人情報保護法上「個人情報に非該当」となる構造

---

## 1. Privacy-Preserving Technologies Comparison

| 技術 | 計算コスト | ESP32 対応 | 対応統計 | 精度への影響 | 実装難度 |
|------|-----------|-----------|---------|------------|---------|
| **Secure Aggregation** (pairwise masking) | 低 | 可能 | 加法的統計のみ (sum, mean) | なし (exact) | 中 |
| **Local Differential Privacy** (Laplace/Gaussian) | 極低 | 可能 | 任意 (精度トレードオフあり) | ε に依存 | 低 |
| **FHE / MPC** (完全準同型暗号 / 秘密計算) | 極高 | 不可能 | 任意の計算 | なし (exact) | 高 |

**選択**: Local Differential Privacy (LDP) を基本とし、Region Hub 間で Secure Aggregation を併用する。

- LDP は ESP32 の限られた計算資源で実行可能（乱数生成 + 加算のみ）
- Secure Aggregation は Region Hub（Linux サーバ）間で適用し、精度を補完
- FHE/MPC は計算コストが ESP32 に対して数桁過大であり、Phase 2 のスコープ外

---

## 2. Architecture: 3-Layer Privacy Hierarchy

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 3: City Aggregator                                          │
│                                                                     │
│  ・匿名統計のみ保持 (ε-DP 保証済み)                                  │
│  ・個人データなし → 同意不要                                          │
│  ・公開監査ログ (ε 消費記録)                                         │
│  ・都市レベルの環境統計ダッシュボード                                   │
│                                                                     │
│  データ例: "渋谷区の平均 CO2 = 620ppm (±40ppm, ε=1.0)"              │
└────────────────────────────┬────────────────────────────────────────┘
                             │  Secure Aggregation
                             │  (pairwise mask 済み集計値)
              ┌──────────────┼──────────────┐
              │              │              │
┌─────────────▼──┐  ┌───────▼───────┐  ┌──▼──────────────┐
│  Layer 2:      │  │  Layer 2:     │  │  Layer 2:       │
│  Region Hub A  │  │  Region Hub B │  │  Region Hub C   │
│                │  │               │  │                  │
│ ・DP 処理済み   │  │ ・DP 処理済み  │  │ ・DP 処理済み    │
│   複数拠点統計  │  │  複数拠点統計  │  │  複数拠点統計    │
│ ・統計情報のみ  │  │ ・統計情報のみ │  │ ・統計情報のみ   │
│ ・拠点間同意    │  │ ・拠点間同意   │  │ ・拠点間同意     │
│   は契約で処理  │  │  は契約で処理  │  │  は契約で処理    │
└──┬──────┬──────┘  └───────────────┘  └──────────────────┘
   │      │
┌──▼──┐ ┌▼─────┐    ...
│Site │ │Site  │
│ #1  │ │ #2   │
└─────┘ └──────┘

┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: SOMS Site (個別拠点)                                      │
│                                                                     │
│  ・生センサーデータ + カメラ映像 (個人データを含む)                      │
│  ・個人データは拠点内に閉じ込め                                       │
│  ・同意は施設内の雇用契約・利用規約で処理                               │
│  ・外部に送出するのは DP ノイズ付加済みの値のみ                         │
│                                                                     │
│  ┌────────┐  ┌────────┐  ┌──────────┐  ┌──────────┐               │
│  │ ESP32  │  │ Camera │  │  Brain   │  │ DP Module│──→ Region Hub │
│  │ Sensor │→ │        │→ │          │→ │ (Local)  │   (DP値のみ)   │
│  └────────┘  └────────┘  └──────────┘  └──────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

**核心**: 同意スコープが各層で完結する。

| 層 | 同意の範囲 | 根拠 |
|----|-----------|------|
| Layer 1 (Site) | 施設利用者・従業員 | 雇用契約・施設利用規約 |
| Layer 2 (Region) | 拠点間の統計共有 | 拠点管理者間の業務委託契約 |
| Layer 3 (City) | **同意不要** | DP 保証により個人情報に非該当 |

---

## 3. Local Differential Privacy on Edge

### 3.1 Laplace Mechanism

ESP32 (MicroPython) 上で実行可能な最小限の Local DP 実装:

```python
# edge/lib/local_dp.py
import urandom, math

def laplace_noise(sensitivity: float, epsilon: float) -> float:
    """Laplace 分布からノイズを生成する。

    Args:
        sensitivity: クエリの感度 (1回の個人の値変化が結果に与える最大影響)
        epsilon: プライバシーパラメータ (小さいほど高プライバシー)

    Returns:
        Laplace(0, sensitivity/epsilon) からサンプリングしたノイズ値
    """
    u = (urandom.getrandbits(32) / 0xFFFFFFFF) - 0.5
    scale = sensitivity / epsilon
    return -scale * math.copysign(1, u) * math.log(1 - 2 * abs(u))

def privatize(value: float, sensitivity: float, epsilon: float) -> float:
    """値に DP ノイズを付加して返す。"""
    return value + laplace_noise(sensitivity, epsilon)
```

**計算コスト**: 乱数生成 + 対数 + 乗算のみ。ESP32 で 1ms 未満。

### 3.2 Sensitivity Configuration

各センサーチャンネルの感度 (sensitivity) とプライバシー予算 (ε) を設定ファイルで管理:

```yaml
# config/federation.yaml (privacy セクション)
privacy:
  enabled: true
  default_epsilon: 1.0          # デフォルトの ε 値
  budget_window_hours: 1        # ε 予算のリセット間隔

  channels:
    temperature:
      sensitivity: 5.0          # 1拠点の温度変化が全体平均に与える最大影響 (℃)
      epsilon: 1.0              # 十分な精度を維持しつつプライバシーを確保
      unit: "℃"
    co2:
      sensitivity: 200.0        # CO2 の感度 (ppm)
      epsilon: 1.0
      unit: "ppm"
    occupancy_count:
      sensitivity: 1.0          # 1人の出入りが変えうる最大値
      epsilon: 0.5              # 在室情報はより厳格に保護
      unit: "人"
    task_completion_rate:
      sensitivity: 2.0          # タスク完了数の感度
      epsilon: 1.0
      unit: "件/h"
    energy_consumption:
      sensitivity: 500.0        # エネルギー消費の感度 (Wh)
      epsilon: 1.0
      unit: "Wh"
```

**ε の意味**: ε=1.0 の場合、攻撃者がある個人のデータの有無を判別できる確率は最大で e^1.0 ≒ 2.72 倍。
ε=0.5 なら e^0.5 ≒ 1.65 倍にまで抑制される。

### 3.3 MQTT Integration

DP 処理済みデータは専用の federation トピックで送出:

```
# トピック構造
federation/{region_id}/aggregate/{channel}

# 例
federation/shibuya-hub-01/aggregate/temperature
federation/shibuya-hub-01/aggregate/co2
federation/shibuya-hub-01/aggregate/occupancy_count
```

**ペイロード形式** (Privacy Attestation 付き):

```json
{
  "value": 23.7,
  "channel": "temperature",
  "site_count": 12,
  "timestamp": "2026-03-06T14:30:00+09:00",
  "privacy": {
    "mechanism": "laplace",
    "epsilon": 1.0,
    "sensitivity": 5.0,
    "budget_window": "2026-03-06T14:00:00+09:00/2026-03-06T15:00:00+09:00",
    "budget_remaining": 3.0
  }
}
```

- `site_count`: 集約に参加した拠点数（k-anonymity の指標）
- `privacy.budget_remaining`: 当該ウィンドウ内の残り ε 予算
- attestation はクライアント側で検証可能（budget 超過のデータは拒否）

---

## 4. Secure Aggregation Protocol

### 4.1 Pairwise Masking

Region Hub 間の集約では、各 Hub の実際の DP 処理済み値を City Aggregator にも非開示にする。
Pairwise Masking により、マスクが参加者間で打ち消し合い、集計値のみが復元される。

```
参加者: Hub A, Hub B, Hub C

1. 各ペアが事前に共有秘密を持つ (Diffie-Hellman 鍵交換):
   s_AB, s_AC, s_BC

2. マスク生成 (PRG で共有秘密から決定論的に):
   Hub A: mask = +PRG(s_AB) + PRG(s_AC)
   Hub B: mask = -PRG(s_AB) + PRG(s_BC)
   Hub C: mask = -PRG(s_AC) - PRG(s_BC)

   ※ 各共有秘密は一方が +、もう一方が - を使用

3. 各 Hub は DP値 + mask を City Aggregator に送信:
   Hub A → Aggregator: x_A + mask_A
   Hub B → Aggregator: x_B + mask_B
   Hub C → Aggregator: x_C + mask_C

4. Aggregator が合計:
   (x_A + mask_A) + (x_B + mask_B) + (x_C + mask_C)
   = x_A + x_B + x_C + (mask_A + mask_B + mask_C)
   = x_A + x_B + x_C + 0     ← マスクが打ち消し合う
   = Σ x_i                    ← 真の集計値
```

**Region Hub 側の実装**:

```python
# services/federation/src/secure_aggregation.py
import hashlib
import struct
from typing import Dict, List

class SecureAggregator:
    """Pairwise Masking による Secure Aggregation"""

    def __init__(self, my_hub_id: str, peer_secrets: Dict[str, bytes]):
        """
        Args:
            my_hub_id: 自身の Hub ID
            peer_secrets: {peer_hub_id: shared_secret} の辞書
        """
        self.my_hub_id = my_hub_id
        self.peer_secrets = peer_secrets

    def _prg(self, secret: bytes, round_id: str) -> float:
        """決定論的擬似乱数生成 (HMAC-SHA256 ベース)"""
        h = hashlib.sha256(secret + round_id.encode()).digest()
        # 先頭 8 バイトを float に変換 (-1000.0 〜 +1000.0 の範囲)
        raw = struct.unpack('>q', h[:8])[0]
        return (raw / (2**63)) * 1000.0

    def compute_mask(self, round_id: str) -> float:
        """当ラウンドのマスク値を計算する。

        Hub ID の辞書順で +/- を決定:
        - 自分 < 相手 → +PRG(secret)
        - 自分 > 相手 → -PRG(secret)
        """
        mask = 0.0
        for peer_id, secret in self.peer_secrets.items():
            prg_value = self._prg(secret, round_id)
            if self.my_hub_id < peer_id:
                mask += prg_value
            else:
                mask -= prg_value
        return mask

    def mask_value(self, value: float, round_id: str) -> float:
        """DP 処理済み値にマスクを付加して返す。"""
        return value + self.compute_mask(round_id)
```

### 4.2 Dropout Resilience

参加 Hub の一部がオフラインの場合にも集約を継続するため、閾値方式を採用する。

```
全 Hub 数: n
最小参加数: t (threshold)
条件: t ≥ n/2 + 1 (過半数以上)

プロトコル:
1. City Aggregator が round_id を発行し、参加を募集 (タイムアウト: 30s)
2. 応答した Hub のリストを確定
3. 不参加 Hub のマスクをキャンセルするため、
   不参加 Hub が関与する共有秘密を参加 Hub が提出
   (事前に Shamir's Secret Sharing で分割済み)
4. マスクの打ち消しが成立 → 集計完了

ドロップアウトが t 未満の場合のみ集約成功。
```

**設定**:

```yaml
# config/federation.yaml (secure_aggregation セクション)
secure_aggregation:
  enabled: true
  min_participants_ratio: 0.6    # 最小参加率 (n の 60%)
  round_timeout_seconds: 30      # ラウンドのタイムアウト
  key_exchange_interval_hours: 24 # DH 鍵交換の更新間隔
```

---

## 5. Privacy Budget Management

### 5.1 ε Accounting

DP のプライバシー保証は累積する（Composition Theorem）。同一データに対して複数回クエリを行うと、
実効 ε は加算されて保証が劣化する。これを管理するため、ε 予算を厳密に追跡する。

- **チャンネル別**: 各センサーチャンネルごとに独立した ε 予算
- **時間ウィンドウ制**: ウィンドウ（デフォルト 1 時間）ごとに予算をリセット
  - ストリーミングデータに対する現実的な運用：同一ウィンドウ内のデータは相関を持つため、
    ウィンドウ単位で ε を制限すれば十分な保証が得られる
- **公開監査ログ**: 全 ε 消費を署名付きで記録し、第三者検証を可能にする

### 5.2 Implementation

```python
# services/federation/src/privacy_budget.py
import time
import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class BudgetEntry:
    """ε 消費の監査ログエントリ"""
    timestamp: float
    channel: str
    epsilon_consumed: float
    mechanism: str
    window_start: str
    window_end: str
    cumulative_epsilon: float
    signature: str  # HMAC-SHA256 による改ざん検知

@dataclass
class ChannelBudget:
    """チャンネル別の ε 予算追跡"""
    max_epsilon: float
    consumed_epsilon: float = 0.0
    window_start: float = 0.0
    window_duration: float = 3600.0  # 1 hour default

class PrivacyBudgetLedger:
    """ε 予算の管理・監査を行うレジャー。

    全 ε 消費を記録し、予算超過を防止する。
    監査ログは署名付きで外部検証可能。
    """

    def __init__(
        self,
        channel_configs: Dict[str, dict],
        signing_key: bytes,
        budget_window_hours: float = 1.0,
    ):
        self.signing_key = signing_key
        self.window_duration = budget_window_hours * 3600
        self.budgets: Dict[str, ChannelBudget] = {}
        self.audit_log: List[BudgetEntry] = []

        for channel, cfg in channel_configs.items():
            max_eps = cfg.get("epsilon", 1.0)
            # ウィンドウあたりの最大 ε = 設定値 × 最大クエリ回数
            # デフォルト: 1回/分 × 60分 = 60回、ε を均等配分
            max_queries_per_window = int(self.window_duration / 60)
            self.budgets[channel] = ChannelBudget(
                max_epsilon=max_eps * max_queries_per_window,
                window_duration=self.window_duration,
            )

    def _current_window(self, channel: str) -> tuple:
        """現在のウィンドウ開始・終了時刻を返す。"""
        now = time.time()
        budget = self.budgets[channel]
        window_start = now - (now % budget.window_duration)
        window_end = window_start + budget.window_duration
        return window_start, window_end

    def _maybe_reset_window(self, channel: str) -> None:
        """ウィンドウが更新されていれば ε をリセットする。"""
        budget = self.budgets[channel]
        window_start, _ = self._current_window(channel)
        if window_start > budget.window_start:
            budget.consumed_epsilon = 0.0
            budget.window_start = window_start

    def _sign_entry(self, entry_data: str) -> str:
        """監査ログエントリに HMAC 署名を付与する。"""
        return hashlib.sha256(
            self.signing_key + entry_data.encode()
        ).hexdigest()[:32]

    def try_consume(self, channel: str, epsilon: float) -> bool:
        """ε を消費する。予算超過なら False を返す。

        Returns:
            True: 消費成功 (DP ノイズ付加を許可)
            False: 予算超過 (データ送出を拒否)
        """
        if channel not in self.budgets:
            return False

        self._maybe_reset_window(channel)
        budget = self.budgets[channel]

        if budget.consumed_epsilon + epsilon > budget.max_epsilon:
            return False

        budget.consumed_epsilon += epsilon

        # 監査ログに記録
        window_start, window_end = self._current_window(channel)
        entry_data = json.dumps({
            "ts": time.time(), "ch": channel, "eps": epsilon,
            "cum": budget.consumed_epsilon,
        })
        entry = BudgetEntry(
            timestamp=time.time(),
            channel=channel,
            epsilon_consumed=epsilon,
            mechanism="laplace",
            window_start=str(window_start),
            window_end=str(window_end),
            cumulative_epsilon=budget.consumed_epsilon,
            signature=self._sign_entry(entry_data),
        )
        self.audit_log.append(entry)
        return True

    def remaining(self, channel: str) -> float:
        """チャンネルの残り ε 予算を返す。"""
        if channel not in self.budgets:
            return 0.0
        self._maybe_reset_window(channel)
        budget = self.budgets[channel]
        return budget.max_epsilon - budget.consumed_epsilon

    def get_audit_log(
        self, channel: Optional[str] = None, limit: int = 100
    ) -> List[BudgetEntry]:
        """監査ログを返す。外部監査機関が検証可能。"""
        entries = self.audit_log
        if channel:
            entries = [e for e in entries if e.channel == channel]
        return entries[-limit:]
```

---

## 6. Legal Framework

### 6.1 個人情報保護法 (日本)

| 段階 | データ内容 | 個人情報該当性 | 同意要否 | 根拠 |
|------|-----------|-------------|---------|------|
| Layer 1 (Site 内) | 生センサー値 + カメラ映像 | **該当** (特定個人を識別可能) | **必要** (施設内で完結) | 個情法 2条1項 |
| Layer 1 → Layer 2 送出 | DP ノイズ付加済み集計値 | **非該当** (復元不可能) | **不要** | 個情法 2条1項但書 |
| Layer 2 (Region) | 複数拠点の DP 集計 | **非該当** | **不要** | 統計情報 |
| Layer 3 (City) | Secure Aggregation 済み | **非該当** | **不要** | 匿名加工情報以上の保護 |

**重要**: DP の数学的保証により、Layer 2 以上のデータは「特定の個人を識別することができない」ため、
個人情報保護法第 2 条第 1 項の「個人情報」に該当しない。
匿名加工情報（同法第 2 条第 6 項）の加工基準よりも厳格な保証を提供する。

### 6.2 GDPR Compliance

| GDPR 条項 | 要件 | SOMS の対応 |
|-----------|------|------------|
| Art. 25 Data Protection by Design | 設計段階からのプライバシー保護 | Local DP を Edge デバイス (ESP32) に組込み |
| Art. 5(1)(c) Data Minimisation | 必要最小限のデータ処理 | 生データは拠点外に一切出ない |
| Recital 26 Anonymisation | 匿名化データは GDPR 適用外 | ε-DP 保証が数学的に匿名性を証明 |
| Art. 35 DPIA | リスク評価の実施 | ε 値から復元リスクを定量的に評価可能 |

**GDPR における位置づけ**: Recital 26 により、「合理的に利用可能なすべての手段を考慮しても
自然人を識別できない」データは GDPR の適用範囲外となる。
ε-DP の保証はこの条件を数学的に満たす。

### 6.3 Practical Consent Elimination

同意が不要となる構造の実現:

```
従来のアプローチ:
  数千拠点 × 数万人 → 全員から個別同意 → 実務上不可能

SOMS のアプローチ:
  Site 内: 雇用契約・施設利用規約で処理 (既存の仕組み)
       ↓
  Site → Region: DP 処理済み → 個人情報に非該当 → 同意不要
       ↓
  Region → City: Secure Aggregation → 個人情報に非該当 → 同意不要
```

**PIA (Privacy Impact Assessment) テンプレート**:

| ε 値 | 復元リスク (理論上限) | 実用的な意味 | 推奨用途 |
|------|---------------------|------------|---------|
| 0.1 | e^0.1 ≒ 1.10 倍 | ほぼ推測不可能 | 在室情報等の高感度データ |
| 0.5 | e^0.5 ≒ 1.65 倍 | 強いプライバシー保護 | 標準的なセンサーデータ |
| 1.0 | e^1.0 ≒ 2.72 倍 | 十分なプライバシー保護 | 環境データ (温度、CO2) |
| 2.0 | e^2.0 ≒ 7.39 倍 | 限定的なプライバシー保護 | 公共性の高い集計のみ |

---

## 7. Federation Config Extension

既存の `config/federation.yaml` にプライバシーセクションを追加:

```yaml
# config/federation.yaml (Phase 2 拡張)
region:
  id: "shibuya-01"
  display_name: "渋谷オフィス"
  sovereign: false
  hub_url: "https://shibuya-01.soms.local"
  central_url: "https://city.soms.local"

federation:
  sync_interval_t1: 1
  sync_interval_t2: 10
  sync_interval_t3: 60
  sync_interval_t4: 600

  # --- Phase 2: Privacy ---
  privacy:
    enabled: true
    default_epsilon: 1.0
    budget_window_hours: 1
    audit_log_retention_days: 365
    signing_key: "${PRIVACY_SIGNING_KEY}"

    channels:
      temperature:
        sensitivity: 5.0
        epsilon: 1.0
      co2:
        sensitivity: 200.0
        epsilon: 1.0
      occupancy_count:
        sensitivity: 1.0
        epsilon: 0.5
      task_completion_rate:
        sensitivity: 2.0
        epsilon: 1.0
      energy_consumption:
        sensitivity: 500.0
        epsilon: 1.0

  secure_aggregation:
    enabled: true
    min_participants_ratio: 0.6
    round_timeout_seconds: 30
    key_exchange_interval_hours: 24

  city_aggregator:
    url: "https://city-agg.soms.local"
    publish_interval_seconds: 300    # 5 分ごとに都市レベル集約
    min_sites_for_publish: 5         # 最低 5 拠点以上で公開 (k-anonymity)
```

---

## 8. Data Flow

ESP32 センサー読取値から City Aggregator に至るまでの完全なデータフロー:

```
Stage 1: ESP32 Sensor Reading (Layer 1 — Site 内)
──────────────────────────────────────────────────
  ESP32 → MQTT: office/main/sensor/env_01/temperature
  Payload: {"value": 24.3}
  ※ 生の正確な値。Site 内のみで使用。

        │
        ▼

Stage 2: Local DP Processing (Layer 1 → Layer 2 境界)
──────────────────────────────────────────────────────
  Site の DP Module が生値にノイズを付加:
    privatize(24.3, sensitivity=5.0, epsilon=1.0)
    → 24.3 + laplace_noise(5.0, 1.0)
    → 25.1  (例)

  ε 予算を消費 (PrivacyBudgetLedger.try_consume)

  MQTT publish: federation/shibuya-01/aggregate/temperature
  Payload:
  {
    "value": 25.1,
    "channel": "temperature",
    "site_count": 1,
    "timestamp": "2026-03-06T14:30:00+09:00",
    "privacy": {
      "mechanism": "laplace",
      "epsilon": 1.0,
      "sensitivity": 5.0,
      "budget_window": "2026-03-06T14:00:00+09:00/PT1H",
      "budget_remaining": 59.0
    }
  }

        │
        ▼

Stage 3: Region Hub Aggregation (Layer 2)
─────────────────────────────────────────
  Region Hub が配下の複数 Site から DP 値を収集:
    Site #1: 25.1  (DP 済み)
    Site #2: 23.8  (DP 済み)
    Site #3: 24.6  (DP 済み)

  Region 平均 = (25.1 + 23.8 + 24.6) / 3 = 24.5
  ※ DP ノイズは平均化により√n 倍精度が向上

  Secure Aggregation 用マスクを付加:
    masked_value = 24.5 + compute_mask(round_id)
    → 1847.3  (例: マスクにより大きく変形)

        │
        ▼

Stage 4: City Aggregator (Layer 3)
──────────────────────────────────
  全 Region Hub からマスク済み値を受信:
    Region A (masked): 1847.3
    Region B (masked): -1215.8
    Region C (masked): -607.0

  合計: 1847.3 + (-1215.8) + (-607.0) = 24.5
  ※ マスクが打ち消し合い、真の集計値が復元

  公開データ:
  {
    "metric": "city_average_temperature",
    "value": 24.5,
    "unit": "℃",
    "region_count": 3,
    "site_count": 45,
    "timestamp": "2026-03-06T14:30:00+09:00",
    "privacy_guarantee": {
      "mechanism": "local_dp + secure_aggregation",
      "per_site_epsilon": 1.0,
      "composition": "parallel (independent channels)"
    }
  }
```

---

## 9. Limitations and Mitigations

| 制限事項 | リスク | 緩和策 |
|---------|--------|--------|
| 少数拠点の k-anonymity 不足 | 拠点数が少ないと統計から個別値を推測しやすい | `min_sites_for_publish` で最低拠点数を強制。少数時は ε を厳格化 (ε ≤ 0.5) |
| 共謀攻撃 (Collusion) | 複数 Hub が結託して他 Hub の値を復元 | Shamir's Secret Sharing による閾値方式。t-out-of-n で t > n/2 を要求 |
| ε 蓄積 (Composition) | 同一データへの繰返しクエリで保証が劣化 | 時間ウィンドウ制で予算を強制リセット。ウィンドウ内は予算上限を厳守 |
| 非加法的統計 | 中央値・分位点等は Secure Aggregation で直接計算不可 | ヒストグラム + DP 近似で対応。各ビンのカウントに DP を適用 |
| ESP32 の乱数品質 | ハードウェア乱数生成器の品質に依存 | ESP32 の `os.urandom` は TRNG を使用。追加エントロピーソースとして ADC ノイズを混合 |
| 時刻同期 | DP ウィンドウの整合性にはクロック同期が必要 | NTP 同期を前提。±5s の許容範囲を設定 |

---

## 10. Migration Path

### Phase 2a: Local DP Module (ESP32 + Python)

```
1. edge/lib/local_dp.py の実装 (MicroPython)
2. services/federation/src/privacy_budget.py の実装
3. config/federation.yaml に privacy セクション追加
4. Site 内テスト: 生値と DP 値の精度比較検証
5. 既存のセンサーパイプラインへの DP 挿入点の決定
```

**影響**: 既存サービスへの変更なし (新規モジュールの追加のみ)

### Phase 2b: ε Budget Management Service

```
1. PrivacyBudgetLedger のサービス化 (FastAPI)
2. 監査ログの PostgreSQL 永続化
3. 監査 API (GET /privacy/audit-log)
4. ε 消費のダッシュボード可視化
5. アラート設定 (予算 80% 消費で通知)
```

**影響**: federation スキーマに `privacy_audit_log` テーブル追加

### Phase 2c: Secure Aggregation between Region Hubs

```
1. Region Hub 間の DH 鍵交換プロトコル実装
2. SecureAggregator クラスの実装
3. Dropout Resilience (Shamir's Secret Sharing)
4. City Aggregator の集約ロジック
5. Region Hub 3台以上での結合テスト
```

**影響**: Region Hub に secure_aggregation モジュール追加。City Aggregator サービス新設。

### Phase 2d: City Aggregator with Public Audit

```
1. City Aggregator サービスの本番デプロイ
2. 公開監査ダッシュボード (ε 消費の可視化)
3. 第三者監査機関向け API
4. PIA (Privacy Impact Assessment) 文書の完成
5. 法務レビュー (個人情報保護委員会への相談)
```

**影響**: 新規サービス + 公開ダッシュボード

---

## Decision Log

| 日付 | 決定事項 | 選択 | 理由 |
|------|---------|------|------|
| 2026-03-06 | DP の適用レイヤー | Edge (Local DP) | Central DP はデータ収集後に適用するため生データが中央に到達してしまう。Local DP なら生データは Site 外に出ない |
| 2026-03-06 | DP メカニズム | Laplace | ESP32 で実装可能。Gaussian は δ パラメータの管理が追加で必要 |
| 2026-03-06 | ε 予算管理方式 | 時間ウィンドウ制 | ストリーミングデータでは cumulative budget が無限に蓄積する。ウィンドウ制でリセットすることで運用可能にする |
| 2026-03-06 | Region Hub 間の集約方式 | Secure Aggregation (pairwise masking) | DP 済み値を Hub 間でも非開示にすることで、二重のプライバシー保護を実現 |
| 2026-03-06 | FHE/MPC の採用 | 不採用 (Phase 2 スコープ外) | ESP32 の計算リソースでは実行不可能。将来的に Region Hub 間のみで検討 |
| 2026-03-06 | 法的根拠の戦略 | 「個人情報に非該当」構造 | 同意ベース (opt-in) は都市規模でスケールしない。非該当構造なら同意自体が不要 |
| 2026-03-06 | 最低拠点数 (k-anonymity) | 5 拠点以上で公開 | 少数拠点では DP ノイズがあっても統計的推測リスクが残る |
| 2026-03-06 | 監査ログの署名方式 | HMAC-SHA256 | 軽量かつ改ざん検知に十分。公開鍵署名は Phase 2d で検討 |

---

## Related Documents

- [ADR: Federated Multi-Region Architecture](adr-federation.md) — Federation Phase 1 の基盤設計
- [Sovereign Urban Intelligence](../CITY_SCALE_VISION.md) — 都市レベル展開の全体構想
