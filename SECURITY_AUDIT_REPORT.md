> ⚠️ **v2 B2B note**: this report covers the v1 code tree. The v2 fork on `main` removed the wallet/economy surfaces and their associated threat model. See `docs/architecture/v2-b2b-migration.md`.

# SOMS セキュリティ監査レポート

**初回監査日**: 2026-02-26
**最終更新日**: 2026-04-04
**対象**: SOMS (Symbiotic Observation & Management System) 全サービス (18サービス)
**手法**: ソースコードレビュー + 構成ファイル分析 (ホワイトボックス)

---

## エグゼクティブサマリー

SOMS は IoT センサー、LLM 意思決定エンジン、仮想通貨経済を統合したオフィス管理システムである。初回監査 (2026-02-26) で **Critical 7件、High 12件、Medium 15件、Low 12件、計46件** の脆弱性を検出した。

2026-04-04 時点の再監査の結果、**16件が修正済み、2件が部分修正、28件が未修正**。新規サービス追加に伴い **3件の新規脆弱性** を検出し、合計 **31件の残存脆弱性** がある。

### 修正状況サマリー

| 重要度 | 検出数 | 修正済み | 部分修正 | 未修正 | 新規 |
|--------|--------|----------|----------|--------|------|
| Critical | 7 | 4 | 2 | 1 | 0 |
| High | 12 | 3 | 1 | 8 | 1 |
| Medium | 15 | 3 | 1 | 11 | 2 |
| Low | 12 | 6 | 0 | 6 | 0 |
| **合計** | **46** | **16** | **4** | **26** | **3** |

### 最も深刻な残存リスク

1. **コンテナセキュリティの欠如**: 全コンテナが root 実行 + rw バインドマウント。Perception は seccomp 無効 + host network
2. **ポート公開**: 9サービスが 0.0.0.0 にバインド (Ollama, VOICEVOX, Backend, Voice 等)
3. **LLM プロンプトインジェクション**: センサーデータ → WorldModel → LLM コンテキストに信頼境界なし

### 初回監査からの主要改善点

1. **認証基盤の確立**: OAuth 2.0 (Slack/GitHub) + JWT + サービス間トークン認証が全面導入
2. **MQTT 認証有効化**: `allow_anonymous false` + パスワード認証
3. **MQTT ポートの localhost 制限**: デフォルト `127.0.0.1` にバインド
4. **パストラバーサル修正**: voice サービスの全音声エンドポイント
5. **OAuth セキュリティ強化**: JSON インジェクション修正、state トークン署名化、リフレッシュトークン family 回転

---

## 攻撃チェーン概要 (更新)

```
┌─────────────────────────────────────────────────────────────────┐
│  Attack Chain 1: 無限通貨発行                    【大幅に緩和】   │
│  ───────────────────────────────                                │
│  旧: POST /transactions/task-reward (認証なし) → 即座に悪用可能   │
│  現: require_service_auth 適用済み。INTERNAL_SERVICE_TOKEN が     │
│      必要。ただしトークン未設定 (空) の開発環境では依然バイパス可能  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Attack Chain 2: LLM 操作によるオフィス制御       【部分的に緩和】 │
│  ──────────────────────────────────                             │
│  旧: MQTT 匿名接続 + 0.0.0.0:1883 → リモートから即攻撃可能      │
│  現: MQTT 認証必須 + 127.0.0.1 バインド。ただし認証情報は         │
│      公知デフォルト値 (soms/soms_dev_mqtt)。ローカルネットワーク   │
│      内の攻撃者は依然として MQTT 経由で LLM を操作可能            │
│      (H-3: プロンプトインジェクション防御なし)                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Attack Chain 3: JWT 偽造による全権限取得          【部分的に緩和】 │
│  ───────────────────────────────                                │
│  旧: デフォルト鍵で即偽造可能                                    │
│  現: 非開発環境では弱い鍵で起動拒否。ただし SOMS_ENV=development  │
│      (デフォルト) では依然としてデフォルト鍵が使用される            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Attack Chain 4: 音声サービス経由のファイル窃取            【解決】│
│  ──────────────────────────────────                             │
│  resolve() + is_relative_to() チェックにより修正済み             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Attack Chain 5 (新規): キオスクモードによる報酬窃取              │
│  ──────────────────────────────────                             │
│  1. GET /tasks/ で未割当タスクを検索                              │
│  2. PUT /tasks/{id}/complete (認証ヘッダーなし)                  │
│  3. assigned_to が NULL のタスクは認証なしで完了可能               │
│  4. ウォレットへの自動報酬支払いがトリガーされる                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 全脆弱性一覧

### Critical (7件: 4件修正済み、2件部分修正、1件未修正)

| ID | 脆弱性 | ファイル | 状態 |
|----|--------|---------|------|
| ~~C-1~~ | ~~全金融エンドポイントが未認証~~ | `services/wallet/src/routers/` | **修正済み** |
| C-2 | [認証バイパス (Optional Auth パターン)](#c-2) | `services/dashboard/backend/routers/tasks.py` | **部分修正** |
| ~~C-3~~ | ~~MQTT 匿名アクセス有効~~ | `infra/mosquitto/mosquitto.conf` | **修正済み** |
| C-4 | [JWT 署名鍵がハードコード公知値](#c-4) | `services/auth/src/config.py` 他 | **部分修正** |
| ~~C-5~~ | ~~MQTT ポートが全インターフェースに公開~~ | `infra/docker-compose.yml` | **修正済み** |
| ~~C-6~~ | ~~タスク完了エンドポイント未認証~~ | `services/dashboard/backend/routers/tasks.py` | **部分修正** → C-2 参照 |
| ~~C-7~~ | ~~OAuth コールバックの JSON インジェクション~~ | `services/auth/src/routers/oauth.py` | **修正済み** |

### High (12件 + 新規1件: 3件修正済み、1件部分修正、9件未修正)

| ID | 脆弱性 | ファイル | 状態 |
|----|--------|---------|------|
| ~~H-1~~ | ~~音声サービスのパストラバーサル~~ | `services/voice/src/main.py` | **修正済み** |
| H-2 | [MQTT トピックインジェクション (LLM 経由)](#h-2) | `services/brain/src/mcp_bridge.py:16` | 未修正 |
| H-3 | [センサーデータ経由のプロンプトインジェクション](#h-3) | `services/brain/src/world_model/` | 未修正 |
| H-4 | [Perception コンテナが seccomp:unconfined + host network](#h-4) | `infra/docker-compose.yml:467-475` | 未修正 |
| H-5 | [全コンテナが root で実行](#h-5) | 全 Dockerfile | 未修正 |
| H-6 | [ソースコードが rw でバインドマウント](#h-6) | `infra/docker-compose.yml` | 未修正 |
| H-7 | [Ollama ポートが認証なしで全公開](#h-7) | `infra/docker-compose.yml:277` | 未修正 |
| H-8 | [VOICEVOX ポートが認証なしで全公開](#h-8) | `infra/docker-compose.yml:141` | 未修正 |
| H-9 | [Dashboard API の一部が未認証](#h-9) | `services/dashboard/backend/routers/` | **部分修正** |
| ~~H-10~~ | ~~CORS ワイルドカード + credentials~~ | `services/dashboard/backend/main.py` | **修正済み** |
| H-11 | [SwitchBot Webhook の署名検証なし](#h-11) | `services/switchbot/src/webhook_server.py:31-57` | 未修正 |
| ~~H-12~~ | ~~自己署名証明書がイメージにベイク~~ | `services/wallet-app/Dockerfile` | **低リスク化** (開発用途) |
| **H-13** | **[Anomaly サービスの管理エンドポイント未認証 (新規)](#h-13)** | `services/anomaly/src/routers/admin.py` | **新規** |

### Medium (15件 + 新規2件: 3件修正済み、1件部分修正、13件未修正)

| ID | 脆弱性 | ファイル | 状態 |
|----|--------|---------|------|
| M-1 | [MQTT ACL なし — 全トピック readwrite](#m-1) | `infra/mosquitto/acl` | 未修正 |
| M-2 | [MQTT 平文通信 (TLS なし)](#m-2) | `infra/mosquitto/mosquitto.conf` | 未修正 |
| M-3 | [zone フィールド未検証 → MQTT トピック操作](#m-3) | `services/dashboard/backend/schemas.py` | 未修正 |
| M-4 | [Pydantic スキーマの入力制約なし](#m-4) | `services/dashboard/backend/schemas.py` | 未修正 |
| ~~M-5~~ | ~~OAuth state トークンがセッション非バインド~~ | `services/auth/src/security.py` | **修正済み** |
| ~~M-6~~ | ~~リフレッシュトークンの再利用検知なし~~ | `services/auth/src/routers/token.py` | **修正済み** |
| M-7 | [無効化ユーザーのトークン検証スキップ](#m-7) | `services/dashboard/backend/jwt_auth.py` | 未修正 |
| M-8 | [nginx セキュリティヘッダー欠如](#m-8) | `services/dashboard/frontend/nginx.conf` | 未修正 |
| M-9 | [トークンが URL フラグメントで配信](#m-9) | `services/auth/src/routers/oauth.py:117-131` | 未修正 |
| M-10 | [リフレッシュトークンを localStorage に保存](#m-10) | `packages/auth/src/AuthProvider.tsx` | 未修正 |
| M-11 | [host.docker.internal が localhost 分離を迂回](#m-11) | `infra/docker-compose.yml` | 未修正 |
| ~~M-12~~ | ~~SQLAlchemy echo=True~~ | `services/dashboard/backend/database.py` | **修正済み** |
| M-13 | [タスクタイトルの自己増幅プロンプトインジェクション](#m-13) | `services/brain/src/main.py` | 未修正 |
| M-14 | [DB デフォルト認証情報のハードコード](#m-14) | `infra/docker-compose.yml` | 未修正 |
| M-15 | [DDL マイグレーションの f-string SQL](#m-15) | `services/dashboard/backend/main.py:39-80` | **部分修正** |
| **M-16** | **[9サービスのポートが 0.0.0.0 にバインド (新規)](#m-16)** | `infra/docker-compose.yml` | **新規** |
| **M-17** | **[INTERNAL_SERVICE_TOKEN のデフォルト空値 (新規)](#m-17)** | `env.example:59` | **新規** |

### Low (12件: 6件修正済み、6件未修正)

| ID | 脆弱性 | ファイル | 状態 |
|----|--------|---------|------|
| L-1 | Swagger UI が本番環境で公開 | 全 FastAPI main.py | 未修正 |
| L-2 | HTTP API レート制限なし | 全 FastAPI サービス | 未修正 |
| L-3 | エラーメッセージが内部情報を露出 | `services/voice/src/main.py` | 未修正 |
| ~~L-4~~ | ~~ログインジェクション (f-string ログ)~~ | `services/brain/src/sanitizer.py` | **修正済み** |
| L-5 | JWT に aud/jti クレームなし | `services/auth/src/security.py` | 未修正 |
| L-6 | Slack OpenID nonce の流用・未検証 | `services/auth/src/providers/slack.py` | 未修正 |
| ~~L-7~~ | ~~MQTT passwd ファイルが world-readable~~ | `infra/mosquitto/passwd` | **低リスク化** (コンテナ内) |
| ~~L-8~~ | ~~SQLite ファイルがソースツリーに残存~~ | — | **修正済み** (削除) |
| ~~L-9~~ | ~~env.example が弱いデフォルト値を正規化~~ | `env.example` | **部分修正** (弱鍵検知追加) |
| ~~L-10~~ | ~~Mock サービスが本番ネットワークを共有~~ | — | **低リスク化** (開発専用) |
| L-11 | HuggingFace トークンが環境変数で露出 | `infra/llm/docker-compose.yml` | 未修正 |
| ~~L-12~~ | ~~Ollama ボリュームが root でマウント~~ | `infra/docker-compose.yml` | **低リスク化** |

---

## 修正済み脆弱性の詳細

### C-1: 全金融エンドポイントが未認証 → 修正済み

**修正内容**: Wallet サービスの全 state-changing エンドポイントに `require_auth` または `require_service_auth` を適用。

```python
# services/wallet/src/jwt_auth.py — 2つの認証戦略
async def require_auth(authorization) -> AuthUser:        # ユーザー認証 (JWT 必須)
async def require_service_auth(auth, x_service_token):    # サービス認証 (JWT or X-Service-Token)
```

**保護されたエンドポイント**:
- `GET /wallets/{user_id}` — `require_auth` + 所有者確認 (自分のウォレットのみ)
- `GET /wallets/{user_id}/history` — `require_auth` + 所有者確認
- `POST /transactions/task-reward` — `require_service_auth`
- `POST /transactions/p2p-transfer` — `require_auth` + 送金元ユーザー確認
- `POST /devices/xp-grant` — `require_service_auth`
- `POST /admin/demurrage/trigger` — `require_auth`
- `PUT /admin/reward-rates/{type}` — `require_auth`

### C-3: MQTT 匿名アクセス → 修正済み

```conf
# infra/mosquitto/mosquitto.conf
allow_anonymous false
password_file /mosquitto/config/passwd
acl_file /mosquitto/config/acl
```

### C-5: MQTT ポート全公開 → 修正済み

```yaml
# infra/docker-compose.yml
ports:
  - "${MQTT_BIND_ADDR:-127.0.0.1}:${SOMS_PORT_MQTT:-1883}:1883"
  - "${MQTT_BIND_ADDR:-127.0.0.1}:${SOMS_PORT_MQTT_WS:-9001}:9001"
```

### C-7: OAuth JSON インジェクション → 修正済み

```python
# services/auth/src/routers/oauth.py (line 118-123)
import json
user_json = urllib.parse.quote(json.dumps({
    "id": user.id,
    "username": user.username,
    "display_name": user.display_name or user.username,
}))
```

### H-1: 音声サービスのパストラバーサル → 修正済み

```python
# services/voice/src/main.py (line 446-451)
def _safe_audio_path(base_dir: Path, filename: str) -> Path:
    """Resolve path and verify it stays within base directory."""
    resolved = (base_dir / filename).resolve()
    if not resolved.is_relative_to(base_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return resolved
```

全 3 エンドポイント (`/audio/{filename}`, `/audio/rejections/{filename}`, `/audio/acceptances/{filename}`) に適用済み。

### H-10: CORS ワイルドカード + credentials → 修正済み

```python
# services/dashboard/backend/main.py (line 22-37)
_cors_origins_raw = os.getenv("CORS_ORIGINS", "")
if _cors_origins_raw:
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(",")]
    _cors_credentials = True
else:
    _cors_origins = ["*"]
    _cors_credentials = False  # ワイルドカード + credentials は CORS 仕様違反なので無効化
```

### M-5: OAuth state トークン → 修正済み (JWT 署名化)

```python
# services/auth/src/security.py (line 48-59)
def create_state_token(nonce: str, origin: str | None = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload: dict = {"nonce": nonce, "exp": exp}
    if origin:
        payload["origin"] = origin
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
```

### M-6: リフレッシュトークン再利用検知 → 修正済み

```python
# services/auth/src/routers/token.py — family-wide revocation
# revoke 時に同一 family_id の全トークンを無効化
family_result = await db.execute(
    select(RefreshToken).filter(
        RefreshToken.family_id == stored.family_id,
        RefreshToken.revoked_at == None,
    )
)
for t in family_result.scalars().all():
    t.revoked_at = datetime.now(timezone.utc)
```

### M-12: SQLAlchemy echo=True → 修正済み

```python
# services/dashboard/backend/database.py
engine = create_async_engine(DATABASE_URL, echo=False)
```

---

## 残存脆弱性の詳細

### <a id="c-2"></a>C-2: 認証バイパス (Optional Auth パターン) — 部分修正

**修正状況**: Wallet サービスは修正済み。Dashboard Backend のタスク完了エンドポイントは「キオスクモード」として意図的に Optional Auth を維持。

**ファイル**: `services/dashboard/backend/routers/tasks.py:337-410`

```python
@router.put("/{task_id}/complete", response_model=schemas.TaskCompleteResponse)
async def complete_task(
    task_id: int,
    body: schemas.TaskComplete = None,
    db: AsyncSession = Depends(get_db),
    auth_user: AuthUser | None = Depends(get_current_user),  # ← Optional
):
    # 認証済みユーザーがいて、タスクが特定ユーザーに割当済みの場合のみ所有者確認
    if auth_user and task.assigned_to and auth_user.id != task.assigned_to:
        raise HTTPException(status_code=403, ...)
```

**リスク**: `assigned_to` が NULL のタスク (未割当) は認証なしで完了でき、報酬支払いがトリガーされる。

**残存エンドポイント**:
- `PUT /tasks/{id}/accept` — Optional auth
- `PUT /tasks/{id}/complete` — Optional auth (報酬支払いトリガー)

---

### <a id="c-4"></a>C-4: JWT 署名鍵がハードコード公知値 — 部分修正

**修正内容**: Auth サービスに弱鍵検出を追加。非開発環境では起動拒否。

```python
# services/auth/src/main.py (line 14-24)
_KNOWN_WEAK_SECRETS = {"soms_dev_jwt_secret_change_me", "changeme", "secret", ""}
if settings.JWT_SECRET in _KNOWN_WEAK_SECRETS:
    if os.getenv("SOMS_ENV") == "development":
        logger.warning("WEAK JWT_SECRET — acceptable only in development mode")
    else:
        raise RuntimeError("JWT_SECRET must be set to a strong, unique value")
```

**残存リスク**:
- `SOMS_ENV` 未設定時のデフォルト動作が不明確 (開発モード扱いになる可能性)
- Dashboard Backend と Wallet サービスには弱鍵検出がない — Auth のみ
- `env.example` に依然としてデフォルト鍵 `soms_dev_jwt_secret_change_me` が記載

---

### <a id="h-2"></a>H-2: MQTT トピックインジェクション — 未修正

**ファイル**: `services/brain/src/mcp_bridge.py:16`

```python
topic = f"mcp/{agent_id}/request/call_tool"
self.mqtt_client.publish(topic, json.dumps(payload))
```

`agent_id` に `/` を含めると任意の MQTT トピックに publish 可能。サニタイザーの `startswith("swarm_hub")` チェックは `swarm_hub/../../evil` で迂回可能。

---

### <a id="h-3"></a>H-3: センサーデータ経由のプロンプトインジェクション — 未修正

**ファイル**: `services/brain/src/world_model/world_model.py`, `services/brain/src/main.py`

MQTT からのセンサーデータ → WorldModel → `get_llm_context()` → LLM のユーザーメッセージに直接埋め込み。信頼境界の分離がない。イベント説明、デバイスID、タスクタイトル、完了レポートすべてが未サニタイズで LLM コンテキストに混入する。

---

### <a id="h-4"></a>H-4: Perception コンテナの特権設定 — 未修正

**ファイル**: `infra/docker-compose.yml:467-475`

```yaml
perception:
    network_mode: host
    security_opt:
      - seccomp:unconfined
    devices:
      - /dev/kfd:/dev/kfd
      - /dev/dri/card1:/dev/dri/card1
      - /dev/dri/renderD128:/dev/dri/renderD128
    group_add:
      - video
```

GPU アクセスのために必要だが、コンテナ脱出のリスクが高い。

---

### <a id="h-5"></a>H-5: 全コンテナが root で実行 — 未修正

全 Python サービスの Dockerfile に `USER` 命令がない。確認済みサービス: brain, wallet, auth, voice, dashboard-backend, switchbot, zigbee2mqtt-bridge, perception, anomaly, wifi-pose。

---

### <a id="h-6"></a>H-6: ソースコードの rw バインドマウント — 未修正

**ファイル**: `infra/docker-compose.yml` (各サービスの volumes)

```yaml
volumes:
  - ../services/brain/src:/app          # デフォルト rw
  - ../services/wallet/src:/app
  - ../services/auth/src:/app
```

---

### <a id="h-7"></a>H-7: Ollama ポートが認証なしで全公開 — 未修正

**ファイル**: `infra/docker-compose.yml:277`

```yaml
ports:
  - "11434:11434"   # 0.0.0.0 にバインド、認証なし
```

---

### <a id="h-8"></a>H-8: VOICEVOX ポートが認証なしで全公開 — 未修正

**ファイル**: `infra/docker-compose.yml:141`

```yaml
ports:
  - "50021:50021"   # 0.0.0.0 にバインド、認証なし
```

---

### <a id="h-9"></a>H-9: Dashboard API の一部が未認証 — 部分修正

**修正状況**: 主要な state-changing エンドポイントに認証が追加されたが、一部は公開のまま。

**保護済み**:
- `POST /tasks/` — `require_service_auth`
- `PUT /tasks/{id}/reminded` — `require_service_auth`
- `PUT /tasks/{id}/dispatch` — `require_service_auth`
- `POST /users/` — `require_service_auth`
- `PUT /users/{id}` — `require_auth` + 所有者確認
- `POST /voice_events/` — `require_service_auth`

**未保護 (公開読み取り)**:
- `GET /tasks/` — 認証不要
- `GET /tasks/queue` — 認証不要
- `GET /tasks/stats` — 認証不要
- `GET /users/` — 認証不要
- `GET /sensors/*` — 認証不要
- `GET /spaces/*` — 認証不要

---

### <a id="h-11"></a>H-11: SwitchBot Webhook の署名検証なし — 未修正

**ファイル**: `services/switchbot/src/webhook_server.py:31-57`

```python
async def _handle_webhook(self, request: web.Request) -> web.Response:
    data = await request.json()
    # ← HMAC 署名検証なし。任意の POST で偽のデバイスイベントを注入可能
```

---

### <a id="h-13"></a>H-13: Anomaly サービスの管理エンドポイント未認証 (新規)

**ファイル**: `services/anomaly/src/routers/admin.py`

新規サービス `anomaly` の管理エンドポイントに認証がない:
- `POST /admin/train` — モデルの再学習トリガー (認証不要)
- `GET /admin/anomalies` — 異常検知結果の参照 (認証不要)

ポートは `127.0.0.1:8009` にバインドされているが、Docker ネットワーク内の全コンテナからアクセス可能。

---

### <a id="m-1"></a>M-1: MQTT ACL — 全トピック readwrite — 未修正

**ファイル**: `infra/mosquitto/acl`

```
user soms
topic readwrite #
topic read $SYS/#
```

全サービスが同一ユーザー `soms` で接続し、全トピックに readwrite アクセス可能。トピック単位の分離がない。

---

### <a id="m-7"></a>M-7: 無効化ユーザーのトークン検証スキップ — 未修正

**ファイル**: `services/dashboard/backend/jwt_auth.py`, `services/wallet/src/jwt_auth.py`

JWT デコード時に `is_active` フィールドを検証しない。無効化されたユーザーの既存 JWT が有効期限まで使用可能。

---

### <a id="m-8"></a>M-8: nginx セキュリティヘッダー欠如 — 未修正

`X-Frame-Options`, `X-Content-Type-Options`, `Content-Security-Policy`, `Referrer-Policy` が全 nginx 設定で未設定。

---

### <a id="m-9"></a>M-9: トークンが URL フラグメントで配信 — 未修正

**ファイル**: `services/auth/src/routers/oauth.py:117-131`

```python
fragment = urllib.parse.urlencode({
    "access_token": access_token,
    "refresh_token": raw_refresh,
    "expires_in": expires_in,
    "user": user_json,
})
redirect_url = f"{frontend_origin}/auth/callback#{fragment}"
```

ブラウザ履歴、Referrer ヘッダー、ブラウザ拡張から漏洩するリスク。

---

### <a id="m-10"></a>M-10: リフレッシュトークンを localStorage に保存 — 未修正

**ファイル**: `packages/auth/src/AuthProvider.tsx`

```typescript
localStorage.setItem(refreshTokenKey, refreshValue);
```

XSS 攻撃でリフレッシュトークンが窃取可能。httpOnly Cookie への移行が推奨される。

---

### <a id="m-15"></a>M-15: DDL マイグレーションの f-string SQL — 部分修正

**ファイル**: `services/dashboard/backend/main.py:39-80`

テーブル名・カラム名がハードコードされたホワイトリストから取得されるよう改善。ただし f-string で `text()` に渡す構造は残存。Alembic への移行が推奨される。

---

### <a id="m-16"></a>M-16: 9サービスのポートが 0.0.0.0 にバインド (新規)

**ファイル**: `infra/docker-compose.yml`

以下のサービスが全インターフェースに公開:

| サービス | ポート | 行 |
|---------|--------|-----|
| Backend (Dashboard API) | 8000 | 90 |
| Frontend (nginx) | 80 | 122 |
| VOICEVOX | 50021 | 141 |
| Voice Service | 8002 | 157 |
| Wallet App | 8004, 8443 | 250-252 |
| Ollama (LLM) | 11434 | 277 |
| Mock LLM | 8001 | 305 |
| SwitchBot Webhook | 8005 | 335 |
| Zigbee2MQTT Frontend | 8008 | 379 |
| Admin Frontend | 8007 | 499 |

**適切に制限済み (127.0.0.1)**:
- PostgreSQL (5432)
- Wallet Service (8003)
- Auth Service (8006)
- Anomaly Service (8009)
- MQTT (1883, 9001)

---

### <a id="m-17"></a>M-17: INTERNAL_SERVICE_TOKEN のデフォルト空値 (新規)

**ファイル**: `env.example:59`

`INTERNAL_SERVICE_TOKEN` のデフォルトが空文字列。空文字列は「トークン未設定」として扱われ、`require_service_auth` が JWT のみをチェックする (サービストークン認証が事実上無効化)。

Voice サービスでは空トークン時に全管理操作が許可される:
```python
# services/voice/src/main.py (line 14-19)
def _verify_service_token(token: str | None) -> None:
    if INTERNAL_SERVICE_TOKEN is None:
        return  # トークン未設定 → 全許可 (開発モード)
```

---

## 評価スコア (更新)

| カテゴリ | 初回 (02/26) | 現在 (04/04) | コメント |
|---------|-------------|-------------|---------|
| 認証・認可 | **1/10** | **5/10** | OAuth+JWT 導入。ただしキオスクモード、新規サービス未認証 |
| 暗号・シークレット管理 | **2/10** | **3/10** | 弱鍵検出追加。TLS なし、デフォルト値依然残存 |
| 入力検証 | **4/10** | **5/10** | パストラバーサル修正。Pydantic 制約・zone 検証は未対応 |
| ネットワーク分離 | **3/10** | **4/10** | MQTT を localhost 化。9サービスが依然 0.0.0.0 |
| コンテナセキュリティ | **2/10** | **2/10** | 変更なし。root 実行、seccomp 無効、rw マウント |
| LLM セキュリティ | **3/10** | **3/10** | 変更なし。プロンプトインジェクション防御なし |
| **総合** | **2.5/10** | **3.7/10** | 認証基盤は大幅改善。コンテナ・LLM セキュリティは未着手 |

---

## 新規サービス・機能の監査結果

### 追加サービス (3件)

| サービス | ポート | 認証 | リスク |
|---------|--------|------|--------|
| anomaly | 127.0.0.1:8009 | なし | 管理エンドポイント未保護 (H-13) |
| wifi-pose | なし (MQTT のみ) | MQTT 認証のみ | 低 |
| admin-frontend | 0.0.0.0:8007 | OAuth + JWT | UI 側は保護済み |

### 追加 LLM ツール (3件)

| ツール | サニタイザー保護 | リスク |
|--------|-----------------|--------|
| `check_inventory` | なし (読み取り専用) | 低 |
| `add_shopping_item` | ホワイトリスト + 20件/時 | 低 |
| `calibrate_shelf` | デバイスID + ステップ + 重量検証 | 低 |

### 監査ログ

`services/brain/src/event_store/writer.py` に包括的な監査ログが実装済み:
- センサーデータ記録 (5秒バッファ + 一括INSERT)
- WorldModel イベント記録
- LLM 決定記録 (サイクル時間、イテレーション数、ツール呼び出し詳細)
- 空間スナップショット (10秒デデュプ)

### サニタイザーの H-5 バグ (レート制限) → 修正済み

**旧**: タイムスタンプがバリデーション前に記録 → 失敗したバリデーションもレート制限を消費
**現**: `record_task_created()` はツール実行成功後にのみ呼び出される (`tool_executor.py:95`)

---

## リファクタリング提案 (優先度更新)

### Phase 1: 即時対応 (1-2日)

#### 1.1 キオスクモードの認証強化

```python
# services/dashboard/backend/routers/tasks.py
# 案1: キオスクモード用の専用トークンを導入
@router.put("/{task_id}/complete")
async def complete_task(
    task_id: int,
    db = Depends(get_db),
    auth_user: AuthUser = Depends(require_auth),  # Optional → Required
):
    if task.assigned_to and auth_user.id != task.assigned_to:
        raise HTTPException(403, "Only the assigned user can complete this task")
```

#### 1.2 Anomaly サービスに認証追加

```python
# services/anomaly/src/routers/admin.py
from jwt_auth import require_service_auth, AuthUser

@router.post("/train")
async def trigger_train(auth_user: AuthUser = Depends(require_service_auth)):
    ...
```

#### 1.3 ポートバインディング修正

```yaml
# docker-compose.yml — 内部専用サービスは localhost のみ
ollama:
    ports: ["127.0.0.1:11434:11434"]
voicevox:
    ports: ["127.0.0.1:50021:50021"]
backend:
    ports: ["127.0.0.1:${SOMS_PORT_BACKEND:-8000}:8000"]
voice-service:
    ports: ["127.0.0.1:${SOMS_PORT_VOICE:-8002}:8000"]
mock-llm:
    ports: ["127.0.0.1:${SOMS_PORT_MOCK_LLM:-8001}:8000"]
```

#### 1.4 INTERNAL_SERVICE_TOKEN の必須化

```python
# env.example
INTERNAL_SERVICE_TOKEN=<generate-with-openssl-rand-hex-32>

# 各サービスで空値を拒否
INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN") or None
if INTERNAL_SERVICE_TOKEN is None:
    logger.warning("INTERNAL_SERVICE_TOKEN not set — service auth disabled")
```

### Phase 2: 短期改善 (1-2週間)

#### 2.1 コンテナセキュリティ強化

```dockerfile
# 全サービス Dockerfile に追加
RUN adduser --disabled-password --gecos "" --uid 1000 appuser
USER appuser
```

```yaml
# docker-compose.yml — read-only マウント
volumes:
  - ../services/brain/src:/app:ro
```

#### 2.2 MQTT トピックインジェクション修正

```python
# services/brain/src/mcp_bridge.py
import re
_SAFE_AGENT_ID = re.compile(r'^[a-zA-Z0-9_.-]+$')

async def call_tool(self, agent_id: str, ...):
    if not _SAFE_AGENT_ID.match(agent_id):
        raise ValueError(f"Invalid agent_id: {agent_id}")
    topic = f"mcp/{agent_id}/request/call_tool"
```

#### 2.3 MQTT ACL の適用

```
# infra/mosquitto/acl
user brain
topic readwrite office/#
topic readwrite mcp/#

user backend
topic write office/+/task_report/#

user perception
topic write office/+/camera/#
topic write office/+/activity/#
topic write office/+/safety/#
```

#### 2.4 nginx セキュリティヘッダー

```nginx
server_tokens off;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; connect-src 'self' ws:" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

#### 2.5 Pydantic スキーマの入力制約

```python
# services/dashboard/backend/schemas.py
class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    bounty_gold: int = Field(10, ge=0, le=10000)
    urgency: int = Field(2, ge=0, le=4)
    zone: Optional[str] = Field(None, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$')
```

### Phase 3: 中期改善 (1-2ヶ月)

| 項目 | 内容 |
|------|------|
| LLM プロンプトインジェクション対策 | センサーデータのサニタイズ + 信頼境界の明確化 |
| 認証アーキテクチャ整理 | Public/User/Service/Admin の 4 レベル |
| リフレッシュトークンを httpOnly Cookie に移行 | localStorage からの脱却 |
| Alembic マイグレーション導入 | 手動 DDL f-string の廃止 |
| SwitchBot Webhook 署名検証 | HMAC-SHA256 検証の追加 |
| is_active ユーザー検証 | JWT デコード後に DB チェック |

### Phase 4: 長期改善 (3ヶ月+)

| 項目 | 内容 |
|------|------|
| MQTT TLS | Let's Encrypt 証明書 + mTLS でデバイス認証 |
| Secret Manager | Docker Secrets or HashiCorp Vault |
| WAF | nginx に ModSecurity 導入 |
| Perception seccomp | カスタムプロファイルの作成 |
| SBOM | 依存ライブラリの CVE 自動チェック |
| ペネトレーションテスト | 外部業者による実環境テスト |

---

## 依存関係監査 (更新: 2026-04-04)

前回監査 (2026-03-08) 以降、依存関係のメジャーバージョン変更なし。

### Python 依存関係 (主要)

| パッケージ | バージョン | 対象サービス | 状態 |
|-----------|-----------|-------------|------|
| FastAPI | 0.135.1 | voice, wallet, auth, dashboard | 最新安定版 |
| uvicorn | 0.41.0 | voice, wallet, auth, dashboard | 最新安定版 |
| aiohttp | 3.13.3 | brain, voice | 最新安定版 |
| SQLAlchemy | 2.0.48 | wallet, auth, dashboard | 最新安定版 |
| asyncpg | 0.31.0 | wallet, auth, dashboard | 最新安定版 |
| Pydantic | 2.12.5 | 全サービス | 最新安定版 |
| PyJWT | 2.11.0 | wallet, auth, dashboard | 最新安定版 |
| paho-mqtt | 2.1.0 (pinned) / >=2.0.0 | 全MQTT系 | 最新安定版 |

### JavaScript 依存関係 (主要)

| パッケージ | バージョン | 対象 | 状態 |
|-----------|-----------|------|------|
| React | 19.2.4 | 全フロントエンド | 最新安定版 |
| TypeScript | ~5.9.3 | 全フロントエンド | 最新安定版 |
| Vite | 7.3.1 | 全フロントエンド | 最新安定版 |
| Tailwind CSS | 4.2.1 | 全フロントエンド | 最新安定版 |
| @tanstack/react-query | 5.90.21 | 全フロントエンド | 最新安定版 |

### 保留中のメジャーアップデート

| パッケージ | 現在 | 最新 | 備考 |
|-----------|------|------|------|
| ESLint | 9.x | 10.x | Breaking changes |
| recharts | 2.15.x | 3.x | admin のみ |
| Ultralytics | ≥8.3.0 | YOLO26 | ROCm 互換性要確認 |

### テスト実行状況

前回: 746 テスト → 現在: **830 テスト** (84テスト増加)

| サービス | テスト数 |
|---------|---------|
| Brain | 189 |
| Auth | 97 |
| Voice | 79 |
| Dashboard | 172 |
| Wallet | 64 |
| SwitchBot | 59 |
| Zigbee2MQTT Bridge | 84 |
| Perception | 86 |

---

## 付録: 攻撃シナリオ詳細 (更新)

### シナリオ A: 経済システム攻撃 (大幅に緩和)

```
旧: 全エンドポイントが未認証 → 無制限に通貨発行可能
現: require_auth / require_service_auth が必要

残存攻撃パス:
1. SOMS_ENV=development + デフォルト JWT 鍵の場合:
   jwt.encode({"sub":"1","iss":"soms-auth","exp":...},
              "soms_dev_jwt_secret_change_me", "HS256")
   → 任意ユーザーの JWT 偽造が可能

2. INTERNAL_SERVICE_TOKEN 未設定の場合:
   サービストークン認証が無効化 → JWT のみで service auth をパス

3. キオスクモード:
   PUT /tasks/{id}/complete (認証なし) → 未割当タスクの報酬を取得
```

### シナリオ B: IoT デバイス制御の奪取 (部分的に緩和)

```
旧: MQTT 匿名 + 0.0.0.0 → リモートから即攻撃可能
現: MQTT 認証必須 + 127.0.0.1

残存攻撃パス (ローカルネットワーク内):
1. デフォルト MQTT 認証情報 (soms/soms_dev_mqtt) でログイン
2. office/# を subscribe → 全センサーデータ傍受
3. mcp/+/request/call_tool に publish → デバイス制御
4. office/{zone}/safety/fall に publish → 偽転倒アラート
   (ACL が全トピック readwrite のため制限なし)
```

### シナリオ C: OAuth アカウント乗っ取り (修正済み)

```
C-7 (JSON インジェクション) は json.dumps() により修正済み。

残存リスク:
- M-9: トークンが URL フラグメントで配信 → ブラウザ履歴からの漏洩
- M-10: リフレッシュトークンが localStorage → XSS で窃取可能
```

---

*以上*
