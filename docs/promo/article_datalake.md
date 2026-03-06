# 都市を覗かずに都市を理解する — 秘密計算とEdge AIによるプライバシー保護型都市データレイク

## 導入: 都市データの価値とジレンマ

都市は呼吸している。

オフィスのCO2は9時に急上昇し、12時に低下し、13時に再び上昇する。商業施設の電力消費は平日と週末で異なる波形を描く。住宅街の気温分布は緑地の配置と強い相関を持つ。これらのデータを都市規模で集約・分析すれば、換気設備の最適配置、エネルギー需給の予測、都市計画への定量的な入力が可能になる。

しかし、この価値を引き出そうとすると、構造的なジレンマに直面する。

都市データの大半は建物の内部で生まれる。CO2濃度、在室人数、エネルギー消費、タスク遂行パターン——これらはすべて建物の占有者の行動に紐づく。集約統計として見れば「オフィス街のCO2平均」だが、生データの段階では「特定のオフィスの、特定の時間帯の、特定の人数の行動パターン」だ。

都市規模でこれを収集するには、すべてのテナント、すべての居住者、すべての施設利用者から同意を得る必要がある。実質的に不可能だ。しかも一度収集したデータは、たとえ匿名化処理を施しても、再識別リスクが残り続ける。

ここに問題の本質がある。**欲しいのは集約統計なのに、取得を強いられるのは個人データである。**

前稿「都市にAIを実装する」では、Core Hubアーキテクチャによる分散型ローカルAIを提案した。各建物にGPU+LLMを配置し、生データをローカルで処理し、City Data Hubには1時間集約の統計値のみを送信する（50,000:1の圧縮比）。この設計はデータ主権を確保するが、法的な問いには完全には答えていなかった。

「集約統計のみを送信する」と言っても、その集約統計が個人情報に該当するなら同意は必要だ。「映像をRAMで処理して即破棄する」と言っても、処理中に個人情報を扱っている事実は変わらない。

本稿では、この法的な隙間を技術的に埋める。**秘密計算（Differential Privacy + Secure Aggregation）をEdgeデバイスレベルで実装し、「個人データが物理的に存在しない」アーキテクチャを構築する。** 結果として、同意を「取りやすくする」のではなく、「不要にする」。

## データクリーンルームという発想

秘密計算によるプライバシー保護は、新しい概念ではない。GoogleのPRISM、AppleのDP実装、金融業界のデータクリーンルームなど、先行事例は多い。

データクリーンルームの基本的な考え方はこうだ。複数の主体が持つデータを、互いに生データを見せることなく、合算結果だけを取得する。TEE（Trusted Execution Environment）やMPC（Multi-Party Computation）を使い、クラウド上の安全な空間でデータを処理する。

しかし、この方式を都市規模のIoTに適用しようとすると、3つの問題が生じる。

**計算コスト。** TEEを使うにはIntel SGXやAMD SEVに対応したサーバーが必要で、MPCは通信ラウンド数が参加者数に比例して増大する。数千台のセンサーが30秒ごとにデータを送信する環境では、中央集権的な秘密計算は計算量が破綻する。

**信頼の前提。** クラウドベースのデータクリーンルームは、クラウド事業者を信頼することが前提だ。TEEのサイドチャネル攻撃の事例（Spectre, Meltdown, PLATYPUS）は、ハードウェアレベルの信頼が絶対的ではないことを示している。都市のデータ主権を外部企業のTEE実装に委ねることは、スマートシティの「データ主権喪失」問題の変形に過ぎない。

**レイテンシ。** センサーデータは鮮度が命だ。CO2が閾値を超えた瞬間に換気を判断する必要があり、クラウドへの往復を挟む余裕はない。

別のアプローチがある。**データを中央に集めて安全に処理するのではなく、データが建物を出る前にプライバシーを数学的に保証する。** データクリーンルームを分散化し、各建物のEdgeデバイスをクリーンルームの入口にする。

## 「個人データが存在しない」アーキテクチャ

Core Hubアーキテクチャに秘密計算を統合した3層プライバシーアーキテクチャを提案する。

```
┌─────────────────────────────────────────────────────────┐
│  Layer 3: City Aggregator                               │
│  匿名統計のみ受信。個人データ: 0                          │
│  「千代田区オフィス街の平均CO2: 620ppm」                   │
└────────────────────────┬────────────────────────────────┘
                         │ Secure Aggregation
                         │ (合算値のみ。個別Hub値は不可視)
          ┌──────────────┼──────────────────┐
          │              │                  │
┌─────────┴──────┐ ┌────┴─────────┐ ┌──────┴─────────┐
│ Layer 2:       │ │ Layer 2:     │ │ Layer 2:       │
│ Region Hub A   │ │ Region Hub B │ │ Region Hub C   │
│ DP処理済み統計  │ │ DP処理済み統計 │ │ DP処理済み統計  │
│ ε-budget管理  │ │ ε-budget管理 │ │ ε-budget管理  │
└───────┬────────┘ └──────┬───────┘ └───────┬────────┘
        │ DP noise added  │                  │
   ┌────┴────┐       ┌────┴────┐        ┌────┴────┐
   │ Layer 1 │       │ Layer 1 │        │ Layer 1 │
   │ Site A  │       │ Site B  │        │ Site C  │
   │ Core Hub│       │ Core Hub│        │ Core Hub│
   │ 生データ │       │ 生データ │        │ 生データ │
   │ ローカル │       │ ローカル │        │ ローカル │
   └─────────┘       └─────────┘        └─────────┘
```

各層の役割と、データの性質の変化を詳細に説明する。

### Layer 1: Site（拠点）— 生データの自治領域

Layer 1は従来のCore Hubと同じだ。センサーの生テレメトリ、カメラ映像、LLMの判断ログ——すべてがこの層に閉じ込められる。生データがLayer 1を離れることは一切ない。

この層では個人データが存在する。CO2値と在室人数の相関から、特定の時間帯の在室パターンが推定できる。しかし、このデータを処理するのは建物内のローカルGPUとLLMであり、外部にアクセス権を持つ主体はいない。

Layer 1の法的位置づけ: 事業者が自身の施設内で、自身のデータを、自身の計算資源で処理する。これは通常のオフィスIT運用と同等であり、特別な同意取得は不要だ（従業員への利用目的の通知は必要）。

### Layer 2: Region Hub — DP処理済みデータの中継

Layer 2が本アーキテクチャの核心だ。Layer 1からLayer 2への遷移で、**Local Differential Privacy（LDP）** が適用される。

具体的には、各Site（Core Hub）がデータをRegion Hubに送信する前に、数学的に校正されたノイズを加える。Region Hubが受け取るのは「ノイズ入りの統計値」であり、元の正確な値を復元することは数学的に不可能だ。

Region Hubは複数のSiteからのDP処理済みデータを集約する。集約によってノイズは平均化され、統計的な有用性は回復するが、個別Siteの正確な値は依然として不可視のままだ。

Layer 2の法的位置づけ: DP処理済みデータは、合理的な手段では個人を識別できないデータであり、個人情報保護法上の「個人情報」に該当しない可能性が高い（後述の法的分析を参照）。

### Layer 3: City Aggregator — 匿名統計の集約

Layer 3では、Region Hub間で**Secure Aggregation**を実行する。各Region Hubが持つ集約値を、互いの個別値を開示することなく合算する。City Aggregatorが得るのは、全Region Hubの合計値のみであり、個別のRegion Hubの値すら復元できない。

Layer 3の法的位置づけ: 匿名統計は明確に個人情報の範囲外であり、同意なしに自由に利用・共有できる。

この3層構造の結果、**個人データはLayer 1を物理的に離れない。** Layer 2以降に存在するのは、数学的にプライバシーが保証されたデータと、暗号学的に安全な集約値のみだ。

## Local Differential Privacy: ESP32で動く秘密計算

Differential Privacy（差分プライバシー、DP）は、「あるデータセットに特定の個人のデータが含まれているかどうかを、統計的に判別できない」ことを数学的に保証する手法だ。

直感的な説明をする。

100人のオフィスのCO2濃度が650ppmだった。ここからあなた1人を除いた99人のCO2濃度はいくらか？ 649ppmか、651ppmか、650ppmか——正確な答えを出すことは、適切なノイズが加わっていれば不可能になる。あなたがいてもいなくても、出力される統計値の分布がほぼ同じになるように設計する。これがDPの核心だ。

### Laplace機構

SOMSで採用するのはLaplace機構だ。真の値に対して、ノイズを加えた値を出力する。

```
x_hat = x + Laplace(0, sensitivity / epsilon)
```

- **sensitivity（感度）**: 1つのデータポイントが結果に与える最大の影響。CO2の場合、1人の在室者が影響を与えるCO2変動の上限値。
- **epsilon（プライバシー予算）**: 小さいほどプライバシー保護が強い。epsilon=1.0は「強い保護」、epsilon=0.1は「非常に強い保護」に相当する。

ノイズの大きさは sensitivity/epsilon に比例する。感度が大きいチャネル（CO2: 個人の影響が大きい）にはより大きなノイズが加わり、感度が小さいチャネル（外気温: 個人の影響がほぼゼロ）にはほとんどノイズが加わらない。

### MicroPython実装

以下は、ESP32上で動作するLocal Differential Privacy実装の概念コードだ。SOMSのEdgeファームウェア（`edge/lib/soms_mcp.py`）に統合可能な形で記述する。

```python
# edge/lib/dp_noise.py
# Local Differential Privacy for ESP32 (MicroPython)
# Laplace noise generation on constrained hardware

import math
import os

# チャネルごとの感度設定
# sensitivity = 1人の個人がそのチャネルに与える最大影響
CHANNEL_SENSITIVITY = {
    "temperature": 0.5,    # 1人の体温による室温変化: +/-0.5 deg C
    "humidity":    2.0,    # 1人の発汗による湿度変化: +/-2%
    "co2":        50.0,    # 1人の呼気によるCO2変化: +/-50ppm
    "occupancy":   1.0,    # 1人 = 1 (整数値)
    "illuminance": 5.0,    # 1人の遮蔽による照度変化: +/-5lux
    "pressure":    0.0,    # 気圧は個人に依存しない -> ノイズ不要
    "voc":        10.0,    # 1人のVOC排出: +/-10
}

# デフォルトepsilon値（チャネルごとに変更可能）
DEFAULT_EPSILON = 1.0


def _laplace_sample(scale):
    """
    Laplace(0, scale) をESP32で生成する。
    os.urandom() を使用してハードウェア乱数から一様分布を生成し、
    逆CDF法でLaplace分布に変換する。
    """
    # os.urandom(4) -> 32bit ハードウェア乱数
    raw = int.from_bytes(os.urandom(4), "big")
    # [0, 2^32 - 1] -> (0, 1) の一様分布（0と1を除外）
    u = (raw + 0.5) / (2**32)
    # 逆CDF: Laplace(0, scale) = -scale * sign(u-0.5) * ln(1 - 2|u-0.5|)
    u_shifted = u - 0.5
    sign = 1.0 if u_shifted >= 0 else -1.0
    noise = -scale * sign * math.log(1.0 - 2.0 * abs(u_shifted))
    return noise


def add_dp_noise(channel, value, epsilon=None):
    """
    観測値にLaplaceノイズを加えてDP処理済み値を返す。

    Args:
        channel: センサーチャネル名 ("temperature", "co2" 等)
        value: 生の観測値 (float)
        epsilon: プライバシー予算 (小さいほど保護が強い)

    Returns:
        float: DP処理済みの値
    """
    sensitivity = CHANNEL_SENSITIVITY.get(channel, 0.0)
    if sensitivity == 0.0:
        # 個人に依存しないチャネル -> ノイズ不要
        return value

    eps = epsilon or DEFAULT_EPSILON
    scale = sensitivity / eps  # Laplace(0, sensitivity/epsilon)
    noise = _laplace_sample(scale)
    return value + noise


def add_dp_noise_batch(readings, epsilon=None):
    """
    複数チャネルの読み取り値を一括でDP処理する。
    SensorSwarm Hubが Leaf からのデータを MQTT に発行する前に呼ぶ。

    Args:
        readings: dict {channel: value}
        epsilon: プライバシー予算

    Returns:
        dict: DP処理済みの {channel: value}
    """
    return {
        ch: add_dp_noise(ch, val, epsilon)
        for ch, val in readings.items()
    }
```

この実装の特筆すべき点は、**ESP32の計算能力で十分に動作する**ことだ。Laplace分布の生成に必要なのは、ハードウェア乱数生成（`os.urandom`）、対数関数（`math.log`）、四則演算のみ。FPUを持たないESP32-S2でもマイクロ秒オーダーで完了する。暗号学的に安全な乱数源はESP32のハードウェアRNGが提供する。

5ドルのマイコンで秘密計算が動く。これがEdge DPの技術的なインパクトだ。

### DP処理の効果

epsilonと感度の設定によるノイズの大きさを具体例で示す。

| チャネル | 真の値 | 感度 | epsilon=1.0 | epsilon=0.5 | epsilon=0.1 |
|---|---|---|---|---|---|
| temperature | 26.0 deg C | 0.5 | 26.0 +/- 0.5 deg C | 26.0 +/- 1.0 deg C | 26.0 +/- 5.0 deg C |
| co2 | 800ppm | 50 | 800 +/- 50ppm | 800 +/- 100ppm | 800 +/- 500ppm |
| occupancy | 5人 | 1.0 | 5 +/- 1人 | 5 +/- 2人 | 5 +/- 10人 |
| pressure | 1013hPa | 0.0 | 1013 +/- 0hPa | 1013 +/- 0hPa | 1013 +/- 0hPa |

（+/-はLaplace分布のscaleパラメータ。実際のノイズは確率的に変動する）

epsilon=1.0の場合、CO2は+/-50ppmの範囲でノイズが加わる。800ppmが750〜850ppmのどこかに見える。この精度で「換気が必要な水準（1000ppm超）かどうか」の判断には十分だが、「正確に何人いるか」の推定は困難になる。

## Secure Aggregation: 合算だけが見える

Local DPは各Siteのプライバシーを保護するが、Region HubからCity Aggregatorへの集約では別の技術が必要になる。Region Hubは複数のSiteからのDP処理済み値を持っており、それ自体は個人情報ではないが、Region Hub単位の集約値は事業者にとって機密性が高い（自社ビルの在室率や稼働パターンが競合に漏れる）。

Secure Aggregationは、**各参加者が自身の値を開示することなく、合計値のみを計算する**プロトコルだ。

### Pairwise Masking Protocol

基本原理は単純だ。2者（AliceとBob）が共有秘密鍵から同じマスク値 r を生成する。Aliceは x_A + r を、Bobは x_B - r を提出する。合計を取ると (x_A + r) + (x_B - r) = x_A + x_B となり、マスクが打ち消される。

N者の場合、各ペアが異なるマスクを使い、全ペアのマスクが合算時に消滅する。

```python
# services/federation/secure_aggregation.py
# Region Hub 間の Secure Aggregation 実装

import hashlib
import hmac
import struct
from typing import Dict, List


class SecureAggregator:
    """
    Pairwise Masking による Secure Aggregation。
    各 Region Hub が自身の集約値を開示せずに、全Hub の合計値を計算する。
    """

    def __init__(self, hub_id: str, peer_ids: List[str],
                 shared_secrets: Dict[str, bytes]):
        self.hub_id = hub_id
        self.peer_ids = peer_ids
        self.shared_secrets = shared_secrets

    def _generate_mask(self, peer_id: str, round_id: str,
                       channel: str) -> float:
        """ペアごとの決定論的マスク生成。"""
        secret = self.shared_secrets[peer_id]
        msg = f"{round_id}:{channel}".encode()
        digest = hmac.new(secret, msg, hashlib.sha256).digest()
        raw = struct.unpack(">Q", digest[:8])[0]
        mask_value = (raw / (2**64)) * 100.0

        if self.hub_id < peer_id:
            return mask_value
        else:
            return -mask_value

    def mask_value(self, value: float, round_id: str,
                   channel: str) -> float:
        """自身の値に全ペアのマスクを加算して提出値を生成する。"""
        total_mask = sum(
            self._generate_mask(peer_id, round_id, channel)
            for peer_id in self.peer_ids
        )
        return value + total_mask

    @staticmethod
    def aggregate(masked_values: List[float]) -> float:
        """全Hub のマスク済み値を合算する。マスクが相殺される。"""
        return sum(masked_values)
```

### Dropout Handling

都市規模のシステムでは、Region Hubの一部がネットワーク障害でオフラインになることは日常だ。ペアワイズマスクの片方が欠けると、マスクが打ち消されず集約結果が壊れる。

対策は閾値秘密分散だ。各Hubが自身のマスク値をShamir's Secret Sharingで他のHubに分散しておく。N個のHub中、t個（閾値）のHubが生存していれば、脱落したHubのマスクを再構成して打ち消すことができる。これにより、一部のHubがオフラインでも残りのHubで安全な集約を継続できる。

SOMSのFederationアーキテクチャでは、Region Hubの最低生存閾値を N/2 + 1（過半数）に設定する。3つのRegion Hubなら、2つが生存していれば集約を継続できる。

## epsilon予算: プライバシーの会計学

Differential Privacyの最も重要な性質は**合成定理（Composition Theorem）**だ。同じデータに対してDP処理を繰り返すと、プライバシー保護は徐々に劣化する。epsilon=1.0のクエリを10回実行すると、全体のプライバシー損失はepsilon=10.0に達する。

これはプライバシーの「予算」だ。使えば減る。使い切ったら、それ以上のクエリを拒否しなければならない。

### チャネル別・時間窓別の予算管理

SOMSのDP実装では、プライバシー予算をチャネルごと・時間窓ごとに管理する。

```python
# services/federation/privacy_budget.py

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Tuple


@dataclass
class ChannelBudget:
    """チャネル単位のプライバシー予算"""
    channel: str
    max_epsilon: float
    consumed_epsilon: float = 0.0
    window_start: datetime = field(default_factory=datetime.utcnow)
    window_duration: timedelta = field(
        default_factory=lambda: timedelta(hours=1)
    )

    def can_spend(self, epsilon: float) -> bool:
        self._maybe_reset_window()
        return (self.consumed_epsilon + epsilon) <= self.max_epsilon

    def spend(self, epsilon: float) -> bool:
        self._maybe_reset_window()
        if (self.consumed_epsilon + epsilon) > self.max_epsilon:
            return False
        self.consumed_epsilon += epsilon
        return True

    def _maybe_reset_window(self):
        now = datetime.utcnow()
        if now - self.window_start >= self.window_duration:
            self.window_start = now
            self.consumed_epsilon = 0.0

    @property
    def remaining(self) -> float:
        self._maybe_reset_window()
        return self.max_epsilon - self.consumed_epsilon


class PrivacyBudgetManager:
    """全チャネルのepsilon予算を一元管理する。"""

    DEFAULT_BUDGETS = {
        "temperature": {"max_epsilon": 4.0, "per_query": 1.0},
        "humidity":    {"max_epsilon": 4.0, "per_query": 1.0},
        "co2":         {"max_epsilon": 2.0, "per_query": 0.5},
        "occupancy":   {"max_epsilon": 1.0, "per_query": 0.25},
        "illuminance": {"max_epsilon": 4.0, "per_query": 1.0},
        "pressure":    {"max_epsilon": float("inf"), "per_query": 0.0},
    }

    def __init__(self):
        self.budgets: Dict[str, ChannelBudget] = {}
        self.audit_log: list = []
        self._init_default_budgets()

    def _init_default_budgets(self):
        for channel, config in self.DEFAULT_BUDGETS.items():
            self.budgets[channel] = ChannelBudget(
                channel=channel,
                max_epsilon=config["max_epsilon"],
            )

    def request_release(self, channel: str,
                        epsilon: float) -> Tuple[bool, str]:
        budget = self.budgets.get(channel)
        if budget is None:
            reason = f"Unknown channel: {channel}"
            self._log(channel, epsilon, False, reason)
            return False, reason

        if not budget.spend(epsilon):
            reason = (
                f"Budget exhausted for {channel}: "
                f"remaining={budget.remaining:.2f}, "
                f"requested={epsilon:.2f}"
            )
            self._log(channel, epsilon, False, reason)
            return False, reason

        self._log(channel, epsilon, True, "approved")
        return True, "approved"

    def get_status(self) -> Dict[str, Dict]:
        """全チャネルの予算状況を返す（公開監査用）"""
        return {
            ch: {
                "max_epsilon": b.max_epsilon,
                "consumed": b.consumed_epsilon,
                "remaining": b.remaining,
                "window_start": b.window_start.isoformat(),
            }
            for ch, b in self.budgets.items()
        }

    def _log(self, channel: str, epsilon: float,
             approved: bool, reason: str):
        self.audit_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "channel": channel,
            "epsilon": epsilon,
            "approved": approved,
            "reason": reason,
        })
```

### ストリーミングデータと予算リセット

IoTセンサーデータには、データベースのクエリ応答とは異なる特性がある。センサーは30秒ごとに値を送信し、古いデータに対する追加クエリは通常発生しない。これはepsilon予算管理にとって有利だ。

時間窓（1時間）が切り替わると予算がリセットされるのは、新しい窓のデータが過去の窓のデータと独立しているからだ。「9時台のCO2」と「10時台のCO2」は異なるデータであり、合成定理は窓内でのみ適用される。

### 公開監査ログ

epsilon予算の消費状況はAPIで公開する。建物のテナント、入居者、監査機関が「このデータからどれだけの情報が外部に漏洩しうるか」を定量的に検証できる。

```
GET /api/federation/privacy-budget

{
  "site_id": "office_shibuya_01",
  "channels": {
    "co2": {
      "max_epsilon": 2.0,
      "consumed": 0.85,
      "remaining": 1.15,
      "window_start": "2026-03-06T09:00:00Z"
    },
    "occupancy": {
      "max_epsilon": 1.0,
      "consumed": 0.25,
      "remaining": 0.75,
      "window_start": "2026-03-06T09:00:00Z"
    }
  }
}
```

「プライバシーを守っている」と主張するのではなく、「epsilonがこの値である」と数値で証明する。これが秘密計算に基づくプライバシー保護の本質的な透明性だ。

## 法的分析: なぜ同意が不要になるか

技術的なプライバシー保護が法的にどう評価されるかを分析する。

### 個人情報保護法（日本）

個人情報保護法第2条第1項は、個人情報を「生存する個人に関する情報であって、当該情報に含まれる氏名、生年月日その他の記述等により特定の個人を識別することができるもの」と定義する。

DP処理済みの「CO2: 823ppm（ノイズ含む）」というデータは、特定の個人を識別できるか？

- **単独での識別**: 不可能。CO2値は個人を識別する記述を含まない。
- **他の情報との照合**: DP処理によりノイズが加わっているため、正確な在室人数の推定は数学的に制限される。epsilonの値が十分に小さければ（epsilon <= 1.0）、照合による識別の成功確率は実質的に無視できる水準になる。
- **容易照合性**: DP処理済みデータから元の個人データへの逆変換は不可能であり、「容易に照合できる」とは言えない。

したがって、**適切なepsilonで処理されたDP出力は、個人情報保護法上の「個人情報」に該当しない**と解釈する余地がある。匿名加工情報（同法第2条第6項）の要件よりも強い保護を数学的に提供している。

### GDPR（EU一般データ保護規則）

GDPRの観点では、2つの条項が重要だ。

**Recital 26（匿名化の定義）**: "The principles of data protection should therefore not apply to anonymous information, namely information which does not relate to an identified or identifiable natural person or to personal data rendered anonymous in such a manner that the data subject is not or no longer identifiable."

DP処理は、データ主体が「もはや識別不可能」な状態に変換する数学的手法であり、Recital 26の匿名化要件を満たす可能性が高い。

**Article 25（Data Protection by Design and by Default）**: "The controller shall [...] implement appropriate technical and organisational measures [...] which are designed to implement data-protection principles, such as data minimisation, in an effective manner."

Edge DPは「設計段階でのデータ保護」の典型例だ。データが生まれた瞬間（ESP32のセンサー読み取り時）にプライバシー保護が適用される。データが建物を離れる前に、設計によって保護が組み込まれている。

### 同意要件の構造的変化

3層アーキテクチャにおける同意要件の変化を整理する。

| 層 | データの性質 | 個人情報該当性 | 同意要件 |
|---|---|---|---|
| Layer 1: Site内 | 生センサーデータ + カメラ映像 | 該当する可能性あり | 事業者内利用の通知（従来と同等） |
| Layer 2: Region Hub | DP処理済み統計（epsilon <= 1.0） | 非該当の可能性が高い | 不要（匿名情報として扱える） |
| Layer 3: City Aggregator | Secure Aggregation後の合計値 | 明確に非該当 | 不要 |

Layer 1は従来のオフィスIT運用と同等の位置づけであり、新たな同意取得は不要だ。Layer 2以降は匿名情報として、個人情報保護法・GDPRの規制対象外となる。

結果として、**都市規模のデータ集約に対して、個別の同意取得は不要になる。** Site単位の利用目的通知（プライバシーポリシー掲示等）で足りる。

## SOMSからの実装パス

現在のSOMSはFederation Phase 1にある。`config/federation.yaml`にregion_idが定義され、全モデルがregion_idカラムを持つ。この基盤の上に、プライバシー保護型データレイクを段階的に構築する。

### Phase 2a: DP Noise Layer

最初のステップは、Core HubからのデータエクスポートにDP処理を追加することだ。

```yaml
# config/federation.yaml (Phase 2a)
region:
  id: "shibuya_office_01"
  display_name: "渋谷オフィス Core Hub"
  sovereign: true
  timezone: "Asia/Tokyo"

privacy:
  enabled: true
  default_epsilon: 1.0
  channels:
    temperature:
      sensitivity: 0.5
      epsilon: 2.0
      window_hours: 1
    co2:
      sensitivity: 50.0
      epsilon: 1.0
      window_hours: 1
    occupancy:
      sensitivity: 1.0
      epsilon: 0.5
      window_hours: 1
    pressure:
      sensitivity: 0.0
      # epsilon不要（個人非依存チャネル）

  budget:
    audit_log: true
    public_endpoint: true
```

### Phase 2b-2d: Region Hub, Secure Aggregation, City Data Lake

```
ESP32 Sensor
  | 生テレメトリ {"value": 26.3}
  | MQTT: office/main/sensor/env_01/temperature
  v
Core Hub (Brain + WorldModel)
  | ローカル処理（LLM判断、Event Store記録）
  | DP処理: add_dp_noise("temperature", 26.3, epsilon=2.0) -> 26.7
  | MQTT: federation/shibuya_01/aggregate/temperature
  v
Region Hub (shibuya)
  | 複数Siteの集約: mean([26.7, 25.1, 27.3]) = 26.4
  | Secure Aggregation mask 追加
  v
City Aggregator
  | 全Region Hubのmasked値を合算 -> maskが相殺
  | 「千代田区+渋谷区+新宿区の平均気温: 25.8 deg C」
  v
City Data Lake (匿名統計のみ)
```

このパスの重要な点は、**既存のSOMSアーキテクチャを破壊しないこと**だ。Layer 1の処理はそのまま維持される。DP処理は出口（federation/ MQTT topic）に追加されるだけであり、Brain、WorldModel、TaskQueue、Voice——すべての既存コンポーネントは変更不要だ。

## 都市の呼吸パターン: 集約統計で見えるもの

匿名の集約統計だけで、都市について何が分かるのか。驚くほど多い。

### CO2 と人の流れ

```
時刻    住宅Hub群    オフィスHub群    商業Hub群
06:00   |||||||..   ...........    ...........
09:00   |||......   ||||||||...    ...........
12:00   ||.......   ||||||.....    |||||......
15:00   ||.......   |||||||||..    |||||||....
18:00   ||||||...   |||........    |||||||||..
21:00   ||||||||.   ...........    ||||.......

（| = 相対CO2レベル、DPノイズ含む）
```

各HubのCO2値にはepsilon=1.0のノイズが加わっているが、Hub群（10拠点以上）の平均を取ることでノイズは平方根N倍に縮小される。10拠点の平均なら、ノイズは約1/3になる。個別のオフィスの在室人数は分からないが、「オフィス街全体が9時に活性化し、18時に沈静化する」というパターンは明確に可視化される。

### エネルギー消費の波

電力消費パターンも同様だ。個別ビルの消費量は機密だが、地域レベルの消費波形は都市計画に必要な情報だ。

- 朝のピーク（暖房/冷房起動）のタイミングと地域差
- 昼食時の一時的な消費低下の深さ
- 夕方のピーク（退勤前のビル設備 + 商業施設のピーク）の重なり
- 週末と平日の波形差

これらは全て、DP処理済みの15分間集約電力値から読み取れる。

### 「見えないけど分かる」

これが本アーキテクチャの核心的な価値だ。個人を覗かずに、集団のパターンを理解する。1つのオフィスの内部は見えない。しかし、1000のオフィスの集約統計から、都市の脈動が浮かび上がる。

プライバシーコスト: 個人データ0バイト。

## 制約と今後の課題

このアーキテクチャには、正直に述べるべき制約がある。

### 小規模サイトの精度問題

epsilonのトレードオフは、サイト規模に強く依存する。100人のオフィスでは、epsilon=1.0のノイズはCO2値に+/-50ppmの影響を与える。これは800ppmの値に対して約6%の誤差であり、実用上問題ない。

しかし、5人の小規模オフィスではどうか。1人が全体の20%を占めるため、感度が実質的に高くなる。対策は2つある。1つは時間集約による精度回復（1時間の120観測値を集約）。もう1つは、小規模サイトではepsilonを大きくする代わりに、送信頻度を下げるというトレードオフ調整だ。

### 結託攻撃

3者のRegion Hub A, B, Cが存在し、AとBが結託してCの値を推定しようとする場合。Secure Aggregationの合計値からAとBの値を引けば、Cの値が算出できる。

対策: DP処理がSecure Aggregationの前段にあるため、Cの「真の」値は既にノイズ入りだ。結託して得られるのはDP処理済みの値であり、元の正確な値ではない。

### 非加法的統計量

Secure Aggregationが直接計算できるのは加法的統計量（合計、カウント、平均）に限られる。中央値、パーセンタイル、分散などの非加法的統計量は、追加のプロトコルが必要だ。実用的には、DP処理済みヒストグラムの集約という代替アプローチがある。

### ハードウェアRNGの信頼性

ESP32のハードウェアRNGは、DP処理の安全性の基盤だ。RNGに偏りがあれば、Laplace分布の生成が不正確になり、プライバシー保証が弱まる。

対策: 定期的なRNG品質テスト（NIST SP 800-22準拠）をファームウェアに組み込み、品質低下を検知した場合はDP処理を停止してデータ送信を止める。「安全でないDPよりも、データなし」が正しいフェイルセーフだ。

## まとめ

本稿で提案したのは、「同意を取りやすくする」技術ではない。**「同意を不要にする」アーキテクチャ**だ。

3層プライバシーアーキテクチャは、生データをLayer 1（Site）に閉じ込め、Layer 2への遷移でLocal Differential Privacyを適用し、Layer 3でSecure Aggregationによる匿名集約を行う。結果として、City Aggregatorが受け取るデータには個人情報が物理的に含まれない。同意が不要になるのは、法を回避するからではなく、**同意を必要とするデータがシステムの外部に存在しなくなる**からだ。

技術が法に対抗するのではない。技術が法の要求を構造的に満たすのだ。

- **プライバシーコスト**: Layer 2以降に流出する個人データ: 0バイト
- **計算コスト**: ESP32上のLaplace分布生成: マイクロ秒オーダー
- **精度コスト**: 10拠点以上の集約でDP由来ノイズは実用上無視可能
- **法的コスト**: 都市規模のデータ集約に個別同意は不要（Site内通知のみ）
- **アーキテクチャコスト**: 既存SOMSへの変更は最小（DP LayerとMQTT topicの追加のみ）

都市を覗かずに、都市を理解する。その技術的な条件は整っている。
