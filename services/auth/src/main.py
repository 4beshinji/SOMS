import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text

from database import engine, Base
from routers import oauth, token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
