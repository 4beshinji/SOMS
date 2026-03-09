"""Extract time series data from hourly_aggregates for model training and inference."""
import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class DataExtractor:
    def __init__(self, engine: AsyncEngine):
        self._engine = engine

    async def get_hourly_series(
        self, zone: str, start: datetime, end: datetime
    ) -> list[dict]:
        """Fetch hourly aggregate data for a zone within a time range.

        Returns a list of dicts with keys: timestamp, avg_temperature, max_temperature, etc.
        """
        async with self._engine.begin() as conn:
            rows = await conn.execute(
                text("""
                    SELECT period_start, zones
                    FROM events.hourly_aggregates
                    WHERE period_start >= :start AND period_start < :end
                    ORDER BY period_start
                """),
                {"start": start, "end": end},
            )

            series = []
            for row in rows:
                period_start = row[0]
                zones_data = row[1]
                if isinstance(zones_data, str):
                    zones_data = json.loads(zones_data)

                if zone not in zones_data:
                    continue

                entry = {"timestamp": period_start}
                entry.update(zones_data[zone])
                series.append(entry)

            return series

    async def get_available_zones(self) -> list[str]:
        """List zones that have data in hourly_aggregates."""
        async with self._engine.begin() as conn:
            rows = await conn.execute(
                text("""
                    SELECT DISTINCT jsonb_object_keys(zones) AS zone
                    FROM events.hourly_aggregates
                    WHERE zones IS NOT NULL AND zones != '{}'::jsonb
                    ORDER BY zone
                """)
            )
            return [row[0] for row in rows]

    async def get_data_coverage(self, zone: str) -> dict:
        """Get data range and density for a zone."""
        async with self._engine.begin() as conn:
            row = await conn.execute(
                text("""
                    SELECT
                        MIN(period_start) AS earliest,
                        MAX(period_start) AS latest,
                        COUNT(*) AS total_rows
                    FROM events.hourly_aggregates
                    WHERE zones ? :zone
                """),
                {"zone": zone},
            )
            result = row.fetchone()
            if not result or result[2] == 0:
                return {"earliest": None, "latest": None, "total_hours": 0, "days": 0}

            earliest = result[0]
            latest = result[1]
            total = result[2]

            if earliest.tzinfo is None:
                earliest = earliest.replace(tzinfo=timezone.utc)
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)

            days = (latest - earliest).total_seconds() / 86400

            return {
                "earliest": earliest.isoformat(),
                "latest": latest.isoformat(),
                "total_hours": total,
                "days": round(days, 1),
            }
