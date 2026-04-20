# v2 B2B Migration — Removing the Credit Economy

## Why v2

SOMS v1 was designed for a voluntary "gamified coworking" model with an
internal credit economy: double-entry ledger, P2P transfers, device XP,
zone multipliers, funding pools, demurrage. In a B2B context where users
are **employees** of the deploying company, that design is legally
unusable:

- Paying employees task bounties in an internal currency conflicts with
  labor-law rules on double compensation, salary taxation, and company
  scrip.
- P2P transfers and any internal currency fall inside the perimeter of
  資金決済法 (Payment Services Act) and securities regulation.
- Device XP and the zone multiplier were never actually used and created
  double-management with the zone-editor UI.

v2 is the B2B fork. The credit economy is removed; task lifecycle is
the only thing that matters; a no-amount audit trail satisfies
compliance.

**v1 remains available** at branch `legacy/v1-with_wallet` and tag
`v1.0-with_wallet` (pushed to `origin`). Check out that tag to see the
full credit-economy implementation.

## What was removed

| Area | v1 | v2 |
|------|----|----|
| Services | `services/wallet/`, `services/wallet-app/` | **deleted** |
| Brain plumbing | `services/brain/src/wallet_bridge.py`, heartbeat forwarding, currency-unit stock | **deleted** |
| LLM tool schema | `create_task.bounty` (500–5000) | **removed** — priority carried by `urgency` (0–4) |
| DB tables (schema `wallet`) | wallets, ledger_entries, devices, device_stakes, funding_pools, pool_contributions, reward_rates, supply_stats | **`DROP SCHEMA wallet CASCADE`** at backend startup |
| DB columns | `tasks.bounty_gold`, `tasks.bounty_xp`, `system_stats.total_xp` | **`ALTER TABLE ... DROP COLUMN`** at backend startup |
| Dashboard UI | bounty/XP badges, reward-multiplier display, QR reward modal, supply header | removed |
| Admin UI | `/economy` route, `EconomyPage`, `DeviceStatusSection` | removed |
| HTTP routes | `/api/wallet/*`, `/transactions/*`, `/devices/xp-grant`, `/devices/zone-multiplier/{zone}` | gone; nginx proxy blocks deleted |
| Integration tests | `test_wallet_integration.py`, `test_demurrage.py`, `test_wallet_dashboard_e2e.py` | deleted |
| Voice service | `currency_unit_stock.py`, `/api/voice/currency-units/*`, bounty in speech prompt | removed |

## What replaces it

### Task assignment

v1 used a bounty-auction model (voluntary accept, reward paid on
complete). v2 uses **admin-assigned tasks** with urgency-based
priority:

- Brain or admin creates a task via `POST /tasks/` with `urgency` in
  0–4.
- Admin (or the accepting user at a kiosk) assigns via
  `PUT /tasks/{id}/accept`. The existing `Task.assigned_to: int` column
  is the single assignment field; no new schema.
- Completing user reports result via `PUT /tasks/{id}/complete` with
  `report_status` + `completion_note`.

No monetary transfer, no reward multiplier. Brain may propose an
assignee in the task description; the admin decides.

### Compliance trail

A new table **`task_audit_log`** in the dashboard DB records each
lifecycle event:

```
id, task_id, action, actor_user_id, notes, region_id, timestamp
```

where `action ∈ { created, accepted, dispatched, completed }`. No
amounts, no currency — this is a pure who/when/what log.

Read endpoints (require JWT):
- `GET /tasks/audit?limit=N` — recent feed across all tasks
- `GET /tasks/{id}/audit` — lifecycle for a single task

The admin SPA surfaces this as the **Activity** tab.

## Task lifecycle (v2)

```
┌──────────┐   POST /tasks/        ┌──────────┐
│ brain or │ ─────────────────────►│  queued  │
│  admin   │  (audit: created)     │  tasks   │
└──────────┘                       └────┬─────┘
                                        │ PUT /{id}/dispatch
                                        │ (audit: dispatched)
                                        ▼
                                   ┌──────────┐
                                   │ dispatched│
                                   └────┬─────┘
                                        │ PUT /{id}/accept
                                        │ (audit: accepted, actor=user_id)
                                        ▼
                                   ┌──────────┐
                                   │ in-prog. │
                                   └────┬─────┘
                                        │ PUT /{id}/complete
                                        │ (audit: completed, actor=user_id,
                                        │  notes=report_status)
                                        │ MQTT: office/{zone}/task_report/{id}
                                        ▼
                                   ┌──────────┐
                                   │  closed  │
                                   └──────────┘
```

## Data-model diff

Dropped columns (v2 startup runs idempotent `ALTER TABLE ... DROP
COLUMN IF EXISTS`):
- `tasks.bounty_gold`
- `tasks.bounty_xp`
- `system_stats.total_xp`

Dropped schema:
- `wallet` (CASCADE)

Added tables:
- `task_audit_log` (created by `Base.metadata.create_all`)

## Service-topology diff

```
v1                                      v2
───────────────────────────────         ───────────────────────────────
brain ──► wallet (heartbeats, XP)       brain (no outbound wallet calls)
brain ──► dashboard (bounty)            brain ──► dashboard (no bounty)
dashboard ──► wallet (payment)          dashboard — audit only
wallet ──► postgres (wallet schema)     (schema dropped)
wallet-app PWA (employee wallet)        (deleted)
admin EconomyPage                       (deleted)
                                        admin ActivityPage (audit feed)
```

Docker-compose services removed: `wallet`, `wallet-app`. Brain and
admin-frontend no longer depend on wallet.

## Inspecting v1

```bash
# see the last v1 commit
git show v1.0-with_wallet --stat | head -30

# browse v1 source without switching branches
git show v1.0-with_wallet:services/wallet/src/main.py | head -80

# check out a working copy for comparison
git worktree add ../soms-v1-legacy legacy/v1-with_wallet
```

## Open items

- `skill_level` / `workload_estimate` on tasks: not added in this
  migration because no caller needs them yet. Revisit if brain starts
  proposing assignees.
- Federation semantics under B2B: `adr-federation.md` talks about
  cross-region reward flow; under v2, federation becomes purely an
  observation/audit topology. A follow-up ADR should rescope.
- Device heartbeat / utility-score tracking: still happens in
  `services/brain/src/device_registry.py` (in-memory, non-financial).
  If operators need a persistent device-health dashboard, expose the
  registry via a new REST endpoint instead of resurrecting wallet's
  `/devices/`.

## Migration commit trail

Six phased commits on `main` after `legacy/v1-with_wallet`:

1. Phase 1 — neuter backend outbound wallet calls
2. Phase 2 — neuter frontend + types + tool registry
3. Phase 3 — introduce task_audit_log (additive)
4. Phase 4 — drop bounty/XP columns + wallet schema (DESTRUCTIVE)
5. Phase 5 — delete wallet services + infra wiring (atomic)
6. Phase 6 — docs sweep + this architecture doc

Each phase is individually committable and leaves the runtime green;
downstream consumers stop calling upstream before upstream is deleted.
