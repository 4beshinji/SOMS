# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [2.0.0] - 2026-04-20 — v2 B2B fork

**BREAKING**: the v1 credit economy was removed to make SOMS deployable in
employment-relationship (B2B) contexts where bounty payments and an internal
currency conflict with labor law and 資金決済法. Legacy preserved at branch
`legacy/v1-with_wallet` and tag `v1.0-with_wallet`. See
[`docs/architecture/v2-b2b-migration.md`](docs/architecture/v2-b2b-migration.md).

### Removed

- `services/wallet/` (double-entry ledger, P2P transfers, device XP, zone
  multiplier, funding pools, demurrage) — 8 DB tables, 25+ HTTP routes
- `services/wallet-app/` (employee PWA)
- `services/brain/src/wallet_bridge.py` and heartbeat → wallet plumbing
- `services/voice/src/currency_unit_stock.py` and `/api/voice/currency-units/*`
- `Task.bounty_gold`, `Task.bounty_xp`, `SystemStats.total_xp` columns
  (dropped via idempotent startup DDL on backend boot)
- Admin Economy page, Dashboard bounty/XP badges + QR reward modal, zone
  multiplier display, device status analytics section
- Integration tests: `test_wallet_integration.py`, `test_demurrage.py`,
  `test_wallet_dashboard_e2e.py`
- Docs: `CURRENCY_SYSTEM.md`, `04_economy_dashboard.md`,
  `wallet-separation.md`, voice `CONTEXT_AWARE_COMPLETION.md`

### Added

- `task_audit_log` table + `/tasks/audit` + `/tasks/{id}/audit` endpoints —
  append-only lifecycle trail (created / accepted / dispatched / completed)
  with no monetary columns; replaces the ledger as the compliance trail
- `ActivityPage` in admin frontend
- `docs/architecture/v2-b2b-migration.md` — canonical v2 reference

### Changed

- `create_task` LLM tool: `bounty` param removed; `urgency` (0–4) carries
  priority alone
- Task assignment: admin-assigned via existing `Task.assigned_to`; v1
  voluntary bounty-auction model is gone
- `docker-compose.yml`: wallet + wallet-app services removed; brain and
  admin-frontend no longer depend on wallet
- nginx: `/api/wallet/` location blocks removed from dashboard and admin
  frontend configs
- `pnpm-workspace.yaml` / `package.json`: wallet-app workspace entry and
  build/dev scripts removed
- CLAUDE.md and README.md rewritten for v2; 15 stale docs tagged with v2
  banner pending full rewrite

## [0.5.0] - 2026-03-06

### Added

- Design brushup with Linear/Notion inspired UI tokens and components (ac68caa)
- Monorepo refactor with shared packages, 3-app architecture, and design unification (c5613eb)
- Privacy-preserving federation ADR and data lake promotional materials (64a389e)

### Changed

- Updated README with Features, ecosystem links, and accurate test counts (0dfe58e)

## [0.4.0] - 2026-02-28

### Added

- Fall detection with furniture-aware discrimination — geometric heuristic with state machine (4d12859)
- Aufheben spatial model — 3-layer architecture with unified `/spaces` API (b442f9c)
- Device status monitoring and occupancy heatmap to analytics dashboard (3c821f9)
- LLM decision timeline chart, error boundary, and authFetch fix (6fcb515)
- Docker smoke test and JWT auth wired into dashboard frontend (1ff0c76)
- Phase 0 completion — 6 parallel streams (5abaa00)
- MTMC person tracking with ArUco calibration (4befd2a)
- OAuth auth service (Slack + GitHub) with JWT-based API protection (93410b2)
- SwitchBot Cloud Bridge service for IoT device integration (8edd9bb)

### Fixed

- Security Phase 1 hardening — auth enforcement, MQTT lockdown, JWT validation, path traversal, OAuth injection prevention (c43d3c6)
- Hardened security across dashboard and wallet services (55024c0)
- Event severity field added, bare excepts fixed, unused spaces router removed (c818caf)
- 3-layer defense against device investigation task spam (b3703ba)
- Build errors resolved and dashboard made auth-free for kiosk mode (86c9be2)

### Removed

- HEMS character configs moved to fork (b8371d0)

## [0.3.0] - 2026-02-20

### Added

- Sensor node enclosure v1 for BME680 and PIR variants (e2ee11c)
- Real office floor plan imported from DXF (345f32e)
- Device trust mechanism to filter unverified devices from LLM context (70dd264)
- Federation Phase 1 region identity across all services (68b433f)
- Sensor visualization and device placement GUI on floor plan (927415b)
- Spatial map service with floor plan visualization (57a95dc)
- Sensor API with repository pattern (7019f41)
- 97 unit tests for auth service (9ddef95)
- 88 unit tests for wallet and dashboard JWT middleware (2131974)
- 47 unit tests for auth-protected endpoints (4a340da)

### Fixed

- HTTPS enabled for wallet-app to allow camera access for QR scanning (7a83645)
- Hard guard for alert suppression to prevent duplicate env tasks (0d92ab7)
- Non-array API response guard in fetchTasks (4e2e01c)

## [0.2.0] - 2026-02-18

### Added

- TanStack Query integration, pnpm migration, hadolint linting (07f77da)
- Port conflict detection and env-var port mapping for startup (741e688)
- Wallet service port 8003 exposed on host (20d8029)

### Fixed

- `os.getenv` URL support and SkipTest cascade guards in e2e tests (800735a)
- Nullable params cast to TEXT in PgSensorRepository queries (816c786)
