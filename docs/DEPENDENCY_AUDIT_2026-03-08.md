# Dependency Audit — 2026-03-08

## Python Updates Applied

### CRITICAL — Security Fixes

| Package | From | To | CVE / Issue | Services |
|---------|------|----|-------------|----------|
| uvicorn | 0.34.3 | 0.41.0 | Critical vulnerability (Snyk) | voice, wallet, auth, dashboard |
| FastAPI | 0.115.14 | 0.135.1 | Starlette DoS fix (0.39–0.41) | voice, wallet, auth, dashboard |
| aiohttp (switchbot) | ≥3.9.0 | ≥3.13.0 | CVE-2025-53643 HTTP smuggling | switchbot |

### Already Current

| Package | Version | Services |
|---------|---------|----------|
| aiohttp | 3.13.3 | brain, voice |
| SQLAlchemy | 2.0.48 | wallet, auth, dashboard |
| asyncpg | 0.31.0 | wallet, auth, dashboard |
| Pydantic | 2.12.5 | all |
| PyJWT | 2.11.0 | wallet, auth, dashboard |
| paho-mqtt | 2.1.0 | perception (pinned); ≥2.0.0 elsewhere |

## JavaScript Updates Applied

Ran `pnpm update --recursive` to pull latest versions within existing semver ranges:

- framer-motion: 12.34.x → 12.35.1
- lucide-react: 0.563.0 → 0.577.0
- tailwind-merge: 3.4.0 → 3.5.0
- postcss: 8.5.6 → 8.5.8
- Other minor/patch bumps resolved via lockfile

## Deferred (Major Version Bumps — Requires Separate Evaluation)

| Package | Current | Latest | Notes |
|---------|---------|--------|-------|
| ESLint | 9.x | 10.x | Breaking changes; affects admin, dashboard, wallet-app |
| recharts | 2.15.x | 3.8.0 | Major API changes; admin only |
| @types/node | 24.x | 25.x | dashboard only |
| @types/qrcode.react | 1.0.5 | 3.0.0 (deprecated) | Consider removing; dashboard only |
| Ultralytics | ≥8.3.0 | YOLO26 | perception; ROCm compatibility check needed |

## Verification

All 746 Python unit tests pass with updated dependencies (189 brain + 97 auth + 79 voice + 172 dashboard + 64 wallet + 59 switchbot + 86 perception).
