"""FastAPI dependency injection for data repositories.

Swap the implementation here to switch storage backends (PG → InfluxDB).
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from .pg_sensor_repository import PgSensorRepository
from .pg_spatial_repository import PgSpatialRepository
from .sensor_repository import SensorDataRepository
from .spatial_repository import SpatialDataRepository


async def get_sensor_repo(
    session: AsyncSession = Depends(get_db),
) -> SensorDataRepository:
    return PgSensorRepository(session)


async def get_spatial_repo(
    session: AsyncSession = Depends(get_db),
) -> SpatialDataRepository:
    return PgSpatialRepository(session)
