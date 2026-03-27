"""Reports API — access to LLM-generated usage reports.

Endpoints expose daily, weekly, and monthly reports stored in
the events.reports table by the brain's ReportGenerator.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/")
async def list_reports(
    report_type: Optional[str] = Query(None, description="Filter by type: daily/weekly/monthly"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List generated reports (most recent first)."""
    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if report_type:
        conditions.append("report_type = :report_type")
        params["report_type"] = report_type

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    result = await db.execute(
        text(f"""
            SELECT id, report_type, period_start, period_end, generated_at,
                   model_used, generation_time_sec, status, summary
            FROM events.reports
            {where}
            ORDER BY period_start DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )

    reports = []
    for row in result:
        reports.append({
            "id": row[0],
            "report_type": row[1],
            "period_start": row[2].isoformat() if row[2] else None,
            "period_end": row[3].isoformat() if row[3] else None,
            "generated_at": row[4].isoformat() if row[4] else None,
            "model_used": row[5],
            "generation_time_sec": row[6],
            "status": row[7],
            "summary": row[8],
        })

    return reports


@router.get("/latest/{report_type}")
async def get_latest_report(
    report_type: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the most recent report of a given type (daily/weekly/monthly)."""
    if report_type not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="report_type must be daily, weekly, or monthly")

    result = await db.execute(
        text("""
            SELECT id, report_type, period_start, period_end, generated_at,
                   model_used, generation_time_sec, status, content, raw_markdown, summary
            FROM events.reports
            WHERE report_type = :report_type AND status = 'completed'
            ORDER BY period_start DESC
            LIMIT 1
        """),
        {"report_type": report_type},
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"No {report_type} report found")

    return _row_to_detail(row)


@router.get("/{report_id}")
async def get_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get full report content by ID."""
    result = await db.execute(
        text("""
            SELECT id, report_type, period_start, period_end, generated_at,
                   model_used, generation_time_sec, status, content, raw_markdown, summary
            FROM events.reports
            WHERE id = :report_id
        """),
        {"report_id": report_id},
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    return _row_to_detail(row)


def _row_to_detail(row) -> dict:
    """Convert a database row to a report detail dict."""
    import json
    content = row[8]
    if isinstance(content, str):
        content = json.loads(content)

    return {
        "id": row[0],
        "report_type": row[1],
        "period_start": row[2].isoformat() if row[2] else None,
        "period_end": row[3].isoformat() if row[3] else None,
        "generated_at": row[4].isoformat() if row[4] else None,
        "model_used": row[5],
        "generation_time_sec": row[6],
        "status": row[7],
        "content": content,
        "raw_markdown": row[9],
        "summary": row[10],
    }
