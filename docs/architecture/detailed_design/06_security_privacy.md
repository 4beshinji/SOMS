# 06. Security, Privacy & Safety

## 1. Safety Philosophy
An autonomous system controlling physical infrastructure must be designed with the assumption that the AI *will* make mistakes (hallucinate) or be compromised. Safety is a foundational layer, not an afterthought.

## 2. Preventing AI Hallucinations

### 2.1 Schema Validation
LLM output is constrained via OpenAI function-calling schema. Tool definitions in `tool_registry.py` specify exact parameter types, ranges, and required fields.

### 2.2 Semantic Sanitation (Sanitizer)
`services/brain/src/sanitizer.py` intercepts every tool call before it reaches the MQTT bus:

- **Range Checks**:
  - `set_temperature(val)`: Valid range `[18, 28]`°C.
  - `run_pump(duration)`: Max `60s`.
  - `create_task(bounty)`: Range `[500, 5000]`.
  - `create_task(urgency)`: Range `[0, 4]`.
- **Rate Limiting**: Max 10 task creations per hour.
- **Parameter Validation**: String length limits, required field checks.
- **Known issue** (H-5): Rate limit timestamps recorded before validation — failed validations consume rate limit quota.

### 2.3 Duplicate Task Prevention
- Brain calls `get_active_tasks` to inject current task list into LLM context.
- Dashboard Backend performs 2-stage duplicate detection (title+location, then zone+task_type).

## 3. Physical & Hardware Safety

### 3.1 Software Limits ("The Fuse")
- **Rate Limiting**: Actuators have software-imposed limits (pump max 60s).
- **Sanity Checks**: Sanitizer rejects outliers (temp > 28°C).
- **ReAct Loop Cap**: Max 5 iterations per cognitive cycle prevents runaway tool calling.

### 3.2 Hardware Safety
- **Water Systems**: Physical float switches cut power on empty/full tank (hardcoded safety).
- **Thermal**: Standard thermal fuses built into heaters.
- **No LLM Bypass**: Critical actuators (electrical locks, main power) are not connected to the system — out of scope for PoC.

## 4. Privacy & Data Protection

### 4.1 Current Implementation
- **No Cloud Uploads**: All video processing happens on the local server (AMD RX 9700 with ROCm).
- **RAM-Only Processing**: Video streams are processed in memory and discarded immediately.
- **No Face Detection**: System uses `person` class (full body bounding box) from COCO pretrained YOLO. No face-specific detection or identification.
- **No Image Persistence**: No frames, snapshots, or video are saved to disk.
- **No Blurring**: Face anonymization is not implemented (not needed since no images are stored).

### 4.2 Perception Data Flow
```
Camera (RTSP) → Perception Service (RAM) → YOLO inference → Structured JSON → MQTT
                 └── Frame discarded immediately after processing
```

Only structured data (person count, activity classification, pose metrics) leaves the Perception service. Raw pixels never reach the Brain or Dashboard.

## 5. Network Security

### 5.1 Current State (PoC)

| Component | Status | Notes |
|-----------|--------|-------|
| MQTT Authentication | **実装済み** | Username/password 認証 (`soms`/`soms_dev_mqtt`) |
| Dashboard Authentication | **Not implemented** | No login, no session management |
| RBAC | **Not implemented** | No roles (User/Admin distinction) |
| VLAN Isolation | **Not implemented** | All services on single Docker bridge `soms-net` |
| TLS | **Not implemented** | All traffic is plaintext |
| PostgreSQL | **制限済み** | `127.0.0.1:5432` にバインド |

### 5.2 Implemented Security Measures

| Measure | Implementation |
|---------|---------------|
| Input validation | Sanitizer module validates all LLM tool calls |
| SQL injection prevention | SQLAlchemy ORM (parameterized queries) |
| Rate limiting | Brain-side: 10 task creations/hour |
| Idempotent payments | Wallet `reference_id` prevents double payment |
| Balance protection | PostgreSQL CHECK constraint: non-system wallets cannot go negative |
| Docker isolation | Services communicate only through `soms-net` bridge network |

### 5.3 Planned Improvements

| Priority | Improvement | Status |
|----------|-------------|--------|
| ~~Medium~~ | ~~PostgreSQL port binding to `127.0.0.1`~~ | **解決済み** |
| ~~Medium~~ | ~~MQTT username/password authentication~~ | **解決済み** (`soms`/`soms_dev_mqtt`) |
| Medium | Dashboard basic auth (nginx) | 未実装 |
| ~~Low~~ | ~~Docker healthchecks for all services~~ | **解決済み** |
| ~~Low~~ | ~~Perception Dockerfile version pinning~~ | **解決済み** |
| Future | VLAN isolation for IoT devices | — |
| Future | TLS for MQTT and HTTP | — |

## 6. Economic System Security

### 6.1 Anti-Gaming
Since there is no visual verification (no `verify_state` tool), the system relies on:
- **Trust model**: Tasks are completed on user declaration.
- **Natural correction**: If conditions persist (e.g., temperature still rising), Brain creates a new task.
- **Idempotent payments**: `reference_id` prevents double reward claims.
- **No real-world value exchange**: Credits have no fiat/crypto exchange, limiting gaming incentive.

### 6.2 Wallet Security
| Property | Mechanism |
|----------|-----------|
| Atomicity | Single SQLAlchemy transaction per transfer |
| Idempotency | `reference_id` duplicate check |
| Deadlock prevention | Wallet ID ascending `FOR UPDATE` lock order |
| Audit trail | All transactions in `ledger_entries` with `balance_after` |
| Negative balance prevention | CHECK constraint (system wallet exempt) |

## 7. Known Security Issues

| ID | Severity | Issue | Status |
|----|----------|-------|--------|
| ~~M-1~~ | ~~Medium~~ | ~~PostgreSQL port exposed on all interfaces~~ | **解決済み** (127.0.0.1 制限) |
| ~~M-2~~ | ~~Medium~~ | ~~MQTT anonymous access enabled~~ | **解決済み** (認証有効化) |
| ~~M-9~~ | ~~Medium~~ | ~~Wallet service port unnecessarily exposed~~ | **解決済み** (127.0.0.1 制限) |
| — | Medium | No authentication on any API endpoint | 未対応 (PoC) |
| — | Low | No audit logging for administrative actions | 未対応 |
| — | Low | Default PostgreSQL password in env.example | 未対応 |

**注**: M-1 (PG 127.0.0.1 制限) と M-2 (MQTT 認証) は解決済み。
