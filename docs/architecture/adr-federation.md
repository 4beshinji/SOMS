# ADR: Federated Multi-Region Architecture (v2)

## Status

Draft (v2). Supersedes the v1 draft which was built around a multi-region
credit economy. v2 removes the wallet / token / stake / demurrage / 51%
semantics — federation in v2 is a **sensor + event + audit-log aggregation
topology**, not a currency topology.

Legacy v1 content is preserved at branch `legacy/v1-with_wallet` and tag
`v1.0-with_wallet`. See `docs/architecture/v2-b2b-migration.md`.

## Context

SOMS v2 is deployed in B2B (employment-relationship) contexts: a single
company may have multiple sites — HQ, branches, labs — each with its own
sensor mesh and CoreHub. The federation question in v2 is narrower than v1:

1. Each site should keep autonomous local LLM + task dispatch.
2. Operators need a single-pane-of-glass view of sensors, events, tasks,
   and task audit logs across sites.
3. Raw sensor data stays local (the original 50,000:1 compression promise);
   only digested / aggregated data flows upward.
4. Authentication and task assignment are scoped to the employee's home
   site, with cross-site visibility only at the ops layer.

There is **no currency**, no cross-region transactions, no reward
multipliers. Regulatory and labor-law concerns that drove v2's B2B fork
remove the need for any of that.

## Requirements

1. **Hybrid operation** — each site runs standalone if the central link
   goes down.
2. **Data aggregation (upward only)** — sensor summaries, LLM decisions,
   task lifecycle events, device health → central; no decisions flow
   downward automatically.
3. **Region identity** — stable `region_id` in all records so multi-region
   joins are unambiguous.
4. **Task audit federation** — the compliance trail added in v2
   (`task_audit_log`) should federate so an auditor can see lifecycle
   events across all sites in one place.

## Core concepts

### Region

Physical SOMS installation unit: one CoreHub, one local Mosquitto, one
dashboard/auth/voice stack, one local Postgres, and the edge devices that
heartbeat into it. Every region carries a `region_id` (e.g. `hq`,
`lab-a`) loaded from `config/federation.yaml`.

```yaml
# config/federation.yaml (non-sovereign site)
region:
  id: "lab-a"
  display_name: "Lab A"
  sovereign: false
  hub_url: "https://lab-a.soms.local"
  central_url: "https://hq.soms.local"
  timezone: "Asia/Tokyo"
  mqtt:
    broker: "mosquitto"
    port: 1883
    bridge_to_central: true
    bridge_topics:
      - "office/#"
```

Sovereign sites omit `central_url` (or set it to their own URL) and set
`sovereign: true`. The sovereign hosts the Federation Hub (§Architecture).

### Identity model

| Concept | Format | Example |
|---|---|---|
| User | `{region_id}:{local_user_id}` | `hq:42`, `lab-a:17` |
| Device | `{region_id}.{device_id}` (once federated) | `hq.env_01` |
| Task `reference_id` | `{region_id}:task:{id}` | `lab-a:task:128` |
| Audit row | carries `region_id` column directly | |

Employees authenticate locally; cross-region viewing happens through
Federation Hub APIs and is op-only. There is no user-to-user cross-region
interaction.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Sovereign Region (hq)                          │
│   Brain, Dashboard, Voice, Auth (all normal v2 services)             │
│   + Federation Hub                                                   │
│       ├─ Region Registry                                             │
│       ├─ Event/Sensor Ingester                                       │
│       ├─ Task Audit Aggregator  (replaces v1 Golden Ledger)          │
│       └─ Cross-region read APIs                                      │
└─────────┬────────────────────────────────┬───────────────────────────┘
          │                                │
   ┌──────▼───────┐                 ┌─────▼────────┐
   │  Region (lab-a)               │  Region (branch-b)              │
   │  Brain/Dashboard/…            │  Brain/Dashboard/…              │
   │  + Region Agent ──→ Fed Hub   │  + Region Agent ──→ Fed Hub     │
   └───────────────┘                 └───────────────┘
```

### Federation Hub (sovereign only)

New service `services/federation/` on the sovereign site:

- **Region Registry** — tracks non-sovereign sites, their health, and
  their public URL.
- **Event/Sensor Ingester** — receives T3/T4 batched data from region
  agents and writes into a `federation.*` schema.
- **Task Audit Aggregator** — receives `task_audit_log` rows from each
  region, maintains a single queryable timeline across all sites.
- **Cross-region read APIs** — serves the ops dashboard.

### Region Agent (non-sovereign)

New sidecar `services/region-agent/` on each non-sovereign site:

- Watches local Postgres for new rows in the v2 tables (`events.*`,
  `sensor_data`, `task_audit_log`) and the brain's `DeviceRegistry`
  snapshot.
- Batches and ships to the Federation Hub over HTTP on the sync tiers
  below.
- Maintains a write-ahead log so offline periods replay cleanly on
  reconnect. Hub dedupes by `event_id`.

## Sync tiers

| Tier | Data | Frequency | Method |
|---|---|---|---|
| T1 | Task audit rows (created/accepted/dispatched/completed) | near-real-time | HTTP push, 5s batch |
| T2 | Device health snapshot, brain LLM decisions | 30s | HTTP push |
| T3 | Sensor telemetry summaries, WorldModel events | 60s batch | HTTP push |
| T4 | Hourly aggregates, spatial heatmaps | 10min batch | HTTP push |

Raw sensor readings stay local. Only summaries and digest data leave the
region — the 50,000:1 compression number from the v1 pitch still holds.

## Data aggregation schema

Federation Hub owns a `federation` schema on the sovereign's Postgres:

```sql
CREATE SCHEMA federation;

CREATE TABLE federation.regions (
    region_id       VARCHAR PRIMARY KEY,
    display_name    VARCHAR NOT NULL,
    is_sovereign    BOOLEAN DEFAULT FALSE,
    hub_url         VARCHAR,
    status          VARCHAR DEFAULT 'active',
    last_sync_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Federated task lifecycle audit (replaces v1 Golden Ledger as the
-- compliance trail). Same columns as the per-region task_audit_log
-- plus region_id + dedup key.
CREATE TABLE federation.task_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID NOT NULL UNIQUE,
    region_id       VARCHAR NOT NULL REFERENCES federation.regions,
    task_id         INTEGER NOT NULL,
    action          VARCHAR(32) NOT NULL,
    actor_user_id   INTEGER,
    notes           TEXT,
    local_timestamp TIMESTAMPTZ NOT NULL,
    central_timestamp TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ix_fed_audit_region ON federation.task_audit_log(region_id);
CREATE INDEX ix_fed_audit_task   ON federation.task_audit_log(region_id, task_id);

CREATE TABLE federation.sensor_summaries (
    id              BIGSERIAL PRIMARY KEY,
    region_id       VARCHAR NOT NULL,
    zone            VARCHAR NOT NULL,
    channel         VARCHAR NOT NULL,
    period_start    TIMESTAMPTZ NOT NULL,
    period_end      TIMESTAMPTZ NOT NULL,
    avg             DOUBLE PRECISION,
    min             DOUBLE PRECISION,
    max             DOUBLE PRECISION,
    count           INTEGER
);

CREATE TABLE federation.device_health (
    global_device_id VARCHAR PRIMARY KEY,  -- "region.device_id"
    region_id       VARCHAR NOT NULL,
    device_type     VARCHAR,
    state           VARCHAR,
    battery_pct     INTEGER,
    power_mode      VARCHAR,
    last_heartbeat  TIMESTAMPTZ
);

CREATE TABLE federation.llm_decisions (
    id              BIGSERIAL PRIMARY KEY,
    region_id       VARCHAR NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    cycle_duration  FLOAT,
    iterations      INTEGER,
    tool_calls      JSONB,
    trigger_events  JSONB
);
```

No ledger, no supply, no stakes — the v1 tables are deliberately absent.

## Federation API

```
POST /federation/sync/audit         # T1: task audit rows
POST /federation/sync/device-health # T2: DeviceRegistry snapshots
POST /federation/sync/llm-decisions # T2: brain cycle logs
POST /federation/sync/sensors       # T3: sensor summaries
POST /federation/sync/heartbeat     # region liveness

POST /federation/regions            # register a region
GET  /federation/regions
PUT  /federation/regions/{id}
DELETE /federation/regions/{id}

GET  /federation/dashboard/audit?region=&task=
GET  /federation/dashboard/sensors?region=&zone=&channel=
GET  /federation/dashboard/device-health?region=
GET  /federation/dashboard/llm-activity?region=&hours=
```

## MQTT federation

MQTT bridging is optional in v2 — federation can run purely through the
HTTP sync API. If low-latency sovereign observation is desired, use a
Mosquitto bridge:

```
# non-sovereign region mosquitto.conf
connection bridge-to-hq
address hq.soms.local:1883
topic office/# out 1 "" lab-a/    # local office/… published as lab-a/office/…
```

Sovereign's brain can then subscribe to `+/office/#` to see all regions'
live sensor streams. This is **observation only**, not control —
cross-region MCP device commands are out of scope in v2.

## Offline mode

Non-sovereign sites are fully autonomous:
- Task dispatch, voice announcements, sensor loop, audit logging continue
  without the hub.
- Region Agent buffers outbound events in a WAL until the hub reappears.
- On reconnect, the hub dedupes by `event_id` and replays.

Nothing blocks on the hub except cross-region queries (which return
"region N last synced at T" when a site is offline).

## Auth

Region-scoped JWTs:

```json
{
  "sub": "42",
  "region_id": "hq",
  "username": "tanaka",
  "display_name": "Tanaka",
  "iss": "soms-auth",
  "exp": 1712345678
}
```

A token issued by one region is valid only at that region's local services.
Federation Hub issues a separate ops-scoped token for cross-region reads.
No cross-region write operations exist for regular users.

## Migration path

Phase F1 is already done in v2: all relevant tables (`tasks`, `users`,
`task_audit_log`, events) carry a `region_id` column defaulting to
`"local"`. Single-region installs work identically before and after
federation lands.

Phase F2 — **Federation Hub skeleton.** `services/federation/` with Region
Registry and the ingest endpoints listed above. No region agents yet;
the sovereign's own data lives in the `federation` schema as region_id
`"local"`.

Phase F3 — **Region Agent + first satellite.** `services/region-agent/`,
WAL, and the T1/T2 sync tiers. Add a second region.

Phase F4 — **T3/T4 sensor and aggregate sync**, MQTT bridge option,
cross-region ops dashboard.

Phase F5 — **Federated JWT / ops-scope tokens**, retention policies on
central, compliance-grade audit trail export.

## Decision log

| Decision | Choice | Reason |
|---|---|---|
| Source of truth for ledger | **N/A — no ledger in v2** | Credit economy removed for B2B |
| Task audit federation | Per-region emit → hub aggregate, dedupe by `event_id` | Compliance needs one queryable timeline |
| Data direction | Upward-only by default | Raw data stays local; sovereign sees digests |
| Sync protocol | HTTP REST (not MQTT) | WAL + retry fits request/response |
| Region ID format | `region:local_id` strings in refs; int user_ids unchanged | Backwards-compat with single-region installs |
| Cross-region writes | None for regular users | Auth / labor-law isolation |
| Auth scope | Region-local tokens + separate ops token | No cross-region identity entanglement |

## Appendix — data volume (v2, per region per day)

Without the wallet tables, per-region shipped volume drops significantly
versus v1:

| Data | Records/day | Shipped size |
|---|---|---|
| Sensor summaries (hourly × 12 zones × 6 channels) | ~1,700 | ~200 KB |
| WorldModel events | ~600 | ~60 KB |
| Task audit rows | ~100 | ~10 KB |
| Device health snapshots (30s × 20 devices) | ~57,000 | ~2 MB (compressed) |
| LLM decisions | ~2,880 | ~1.4 MB |
| **Total shipped** | | **~4 MB/day/region** |

10 regions → ~40 MB/day into the sovereign. Trivial for any modern stack.
