import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text

from database import engine, Base
from routers import oauth, token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


_KNOWN_WEAK_SECRETS = {"soms_dev_jwt_secret_change_me", "changeme", "secret", ""}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from config import settings
    if settings.JWT_SECRET in _KNOWN_WEAK_SECRETS:
        if os.getenv("SOMS_ENV", "production") != "development":
            raise RuntimeError("JWT_SECRET must be set to a strong, unique value")
        logger.warning("WEAK JWT_SECRET — acceptable only in development mode")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Auth service started — tables ready")
    yield


app = FastAPI(title="SOMS Auth Service", lifespan=lifespan)

app.include_router(oauth.router)
app.include_router(token.router)


@app.get("/")
async def root():
    return {"message": "SOMS Auth Service Running"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth"}
