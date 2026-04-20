import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from database import engine, Base
from routers import tasks, users, voice_events, sensors, spatial, devices, shopping, inventory, reports, chat, displays, coordination
import models # Make sure models are registered

logger = logging.getLogger(__name__)

_KNOWN_WEAK_SECRETS = {"soms_dev_jwt_secret_change_me", "changeme", "secret", ""}

app = FastAPI(title="SOMS Dashboard API")

# CORS configuration
# Set CORS_ORIGINS to a comma-separated list of allowed origins in production.
# e.g. CORS_ORIGINS=https://office.example.com,https://wallet.example.com
# Wildcard ("*") cannot be combined with credentials — allow_credentials is
# only enabled when explicit origins are configured.
_cors_origins_raw = os.getenv("CORS_ORIGINS", "")
if _cors_origins_raw:
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
    _cors_credentials = True
else:
    _cors_origins = ["*"]
    _cors_credentials = False  # wildcard + credentials violates CORS spec

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _migrate_add_columns(conn):
    """Add missing columns to existing tables (stopgap until Alembic)."""
    insp = inspect(conn)

    # Collect existing columns per table
    table_columns = {}
    for table_name in insp.get_table_names():
        table_columns[table_name] = {c["name"] for c in insp.get_columns(table_name)}

    # (table, column, SQL type, default_expr_or_None)
    migrations = [
        ("tasks", "assigned_to", "INTEGER", None),
        ("tasks", "accepted_at", "TIMESTAMP WITH TIME ZONE", None),
        ("tasks", "report_status", "VARCHAR", None),
        ("tasks", "completion_note", "VARCHAR", None),
        ("users", "display_name", "VARCHAR", None),
        ("users", "is_active", "BOOLEAN", "TRUE"),
        ("users", "created_at", "TIMESTAMP WITH TIME ZONE", "NOW()"),
        ("tasks", "region_id", "VARCHAR(32)", "'local'"),
        ("users", "region_id", "VARCHAR(32)", "'local'"),
        ("users", "global_user_id", "VARCHAR(200)", None),
        ("tasks", "audience", "VARCHAR(16)", "'user'"),
        ("device_positions", "orientation_deg", "DOUBLE PRECISION", None),
        ("device_positions", "fov_deg", "DOUBLE PRECISION", None),
        ("device_positions", "detection_range_m", "DOUBLE PRECISION", None),
        ("device_positions", "label", "VARCHAR", None),
        ("device_positions", "context", "TEXT", None),
        ("voice_events", "target_zone", "VARCHAR", None),
        ("voice_events", "target_display_ids", "VARCHAR", None),
    ]
    # Allowlisted identifiers — only these table/column names are permitted
    _ALLOWED_TABLES = {m[0] for m in migrations}
    _ALLOWED_COLUMNS = {m[1] for m in migrations}

    for table, col_name, col_type, default in migrations:
        if table not in _ALLOWED_TABLES or col_name not in _ALLOWED_COLUMNS:
            continue
        if table in table_columns and col_name not in table_columns[table]:
            default_clause = f" DEFAULT {default}" if default else ""
            # Safe: table/col_name/col_type are from hardcoded allowlist above
            conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}{default_clause}"
            ))
            logger.info("Migrated: added column %s.%s", table, col_name)


# Startup Event
@app.on_event("startup")
async def startup():
    # JWT secret validation
    jwt_secret = os.getenv("JWT_SECRET", "")
    if jwt_secret in _KNOWN_WEAK_SECRETS:
        if os.getenv("SOMS_ENV") == "development":
            logger.warning("WEAK JWT_SECRET — acceptable only in development mode")
        else:
            raise RuntimeError("JWT_SECRET must be set to a strong, unique value (set SOMS_ENV=development to bypass)")

    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        # Add columns that create_all cannot add to existing tables
        await conn.run_sync(_migrate_add_columns)
        # Ensure events schema exists (owned by brain, read by sensors API)
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS events"))
        # v2 drop-column migrations (one-way, idempotent). Legacy v1 data is
        # preserved in branch `legacy/v1-with_wallet` / tag `v1.0-with_wallet`.
        await conn.execute(text("ALTER TABLE IF EXISTS tasks DROP COLUMN IF EXISTS bounty_gold"))
        await conn.execute(text("ALTER TABLE IF EXISTS tasks DROP COLUMN IF EXISTS bounty_xp"))
        await conn.execute(text("ALTER TABLE IF EXISTS system_stats DROP COLUMN IF EXISTS total_xp"))
        await conn.execute(text("DROP SCHEMA IF EXISTS wallet CASCADE"))


# Include Routers
app.include_router(tasks.router)
app.include_router(users.router)
app.include_router(voice_events.router)
app.include_router(sensors.router)
app.include_router(spatial.router)
app.include_router(devices.router)
app.include_router(shopping.router)
app.include_router(inventory.router)
app.include_router(reports.router)
app.include_router(chat.router)
app.include_router(displays.router)
app.include_router(coordination.router)

@app.get("/")
async def root():
    return {"message": "SOMS Dashboard API Running"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "dashboard-backend"}
