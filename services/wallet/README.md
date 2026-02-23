# Wallet Service

SOMS の信用経済エンジン。複式帳簿による厳密なクレジット管理、デバイス XP スコアリング、投資モデルを提供する。

- **ポート**: `127.0.0.1:8003` (ホスト限定) → コンテナ内 `8000`
- **Swagger UI**: `http://localhost:8003/docs`

## 設計思想

| 概念 | 説明 |
|------|------|
| 複式帳簿 | すべての移動は借方・貸方のペアで記録。残高の不整合が原理的に起こらない |
| システムウォレット | `user_id=0` が発行源。タスク報酬はここから支払われる |
| デバイス XP | センサーデバイスは稼働実績に応じて XP を蓄積し、報酬乗数が増加 |
| 投資モデル | デバイスに株式を発行。オーナー 50% + 投資家比例分配 |
| デマレージ | 未使用クレジットには 2%/日 の保有コストがかかる (流通促進) |

## API エンドポイント

### ウォレット (`/wallets`)

| Method | Path | 説明 |
|--------|------|------|
| POST | `/wallets/` | ウォレット作成 |
| GET | `/wallets/{user_id}` | 残高照会 |
| GET | `/wallets/{user_id}/history` | 取引履歴 |

### 取引 (`/transactions`)

| Method | Path | 説明 |
|--------|------|------|
| POST | `/transactions/task-reward` | タスクバウンティ支払い (システムウォレット → ユーザー) |
| POST | `/transactions/p2p-transfer` | P2P 送金 (手数料あり) |
| GET | `/transactions/transfer-fee` | 送金手数料プレビュー |
| GET | `/transactions/{transaction_id}` | 取引詳細 |

### デバイス (`/devices`)

| Method | Path | 説明 |
|--------|------|------|
| POST | `/devices/` | デバイス登録 |
| GET | `/devices/` | デバイス一覧 (XP・乗数・残高付き) |
| PUT | `/devices/{device_id}` | デバイスメタデータ更新 |
| POST | `/devices/xp-grant` | ゾーン内全デバイスに XP 付与 |
| POST | `/devices/{device_id}/heartbeat` | ハートビート記録・インフラ報酬付与 |
| POST | `/devices/{device_id}/utility-score` | ユーティリティスコア更新 |
| GET | `/devices/zone-multiplier/{zone}` | ゾーン報酬乗数取得 |

### 投資モデル (`/devices/{id}/funding`, `/devices/{id}/stakes`)

| Method | Path | 説明 |
|--------|------|------|
| POST | `/devices/{device_id}/funding/open` | 株式公開 (資金調達開始) |
| POST | `/devices/{device_id}/funding/close` | 資金調達終了 |
| POST | `/devices/{device_id}/stakes/buy` | 株式購入 |
| POST | `/devices/{device_id}/stakes/return` | 株式返却 (売却) |
| GET | `/devices/{device_id}/stakes` | ステークホルダー一覧 |
| GET | `/users/{user_id}/portfolio` | ユーザーのポートフォリオ |

### 供給統計 & デマレージ

| Method | Path | 説明 |
|--------|------|------|
| GET | `/supply` | 発行量・焼却量・流通量 |
| POST | `/demurrage/trigger` | デマレージサイクル手動実行 |

## XP スコアリング

デバイスの報酬乗数は XP と稼働実績から動的に計算される。

```
乗数 = 1.0x ~ 3.0x
  └─ ハードウェアスコア (センサー種類・数)
  └─ ユーティリティスコア (Brain が /devices/{id}/utility-score で更新)
  └─ 稼働時間 (累積ハートビート)
```

高品質なセンサーデータを長期間提供するデバイスほど高い乗数を得る。

## 投資報酬の分配

タスク完了時のバウンティ支払いフロー:

```
1. Dashboard: POST /transactions/task-reward  (タスク ID + 金額)
2. Wallet: システムウォレット → ユーザーウォレットへ送金
3. デバイス比例分配 (デバイス投資がある場合):
   オーナー: 50% 固定
   投資家:   残り 50% を持株比率で分配
```

## データモデル

```
Wallet: user_id, balance (Decimal)
LedgerEntry: debit_wallet_id, credit_wallet_id, amount, memo, created_at
Device: device_id, zone, owner_id, xp, utility_score, multiplier
DeviceStake: device_id, user_id, shares (現在保有株数)
FundingPool: device_id, total_shares, share_price, status (open/closed)
PoolContribution: pool_id, user_id, shares_bought
SupplyStats: total_issued, total_burned, circulating
```

## 設定

| 環境変数 | デフォルト | 説明 |
|---------|-----------|------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL 接続 |
| `JWT_SECRET` | — | JWT 検証 (Auth サービスと共有) |
| `SYSTEM_WALLET_BALANCE` | 1,000,000 | システムウォレット初期残高 |

## 起動・ログ確認

```bash
docker logs -f soms-wallet
# API ドキュメント
open http://localhost:8003/docs
```

## テスト

```bash
# 統合テスト (サービス起動必要)
.venv/bin/python infra/tests/integration/test_wallet_integration.py

# E2E テスト (Wallet + Dashboard 連携)
.venv/bin/python infra/tests/e2e/test_wallet_dashboard_e2e.py
```

Phase 1.5 完了時点でのテスト結果: 52テスト全通過 (commit `53a6157`)
