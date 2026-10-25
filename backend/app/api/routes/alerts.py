"""Alerts API routes.

Endpoints
---------
GET    /api/v1/alerts                  List alerts (filter: run_id, severity, limit).
GET    /api/v1/alerts/summary          Aggregate counts.
DELETE /api/v1/alerts                  Purge all alerts.

The legacy ``GET ""`` route delegates to AlertService so existing callers that
relied on MockIntegration.list_alerts() still receive a valid ``{"items": [...]}``
response — now backed by the real SQLite table.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.modules.alerts.schemas import AlertOut, AlertSummary
from app.modules.alerts.service import AlertService

router = APIRouter()

_svc = AlertService()


@router.get("")
async def list_alerts(
    run_id: Optional[str] = Query(None, description="Filter by detection run ID."),
    severity: Optional[str] = Query(None, description="Filter by severity level."),
    limit: int = Query(100, ge=1, le=10_000, description="Maximum rows to return."),
) -> dict:
    """Return a list of alert records, optionally filtered by run_id and severity."""
    items = await _svc.list_alerts(run_id=run_id, severity=severity, limit=limit)
    return {"items": [a.model_dump() for a in items]}


@router.get("/summary")
async def alert_summary(
    run_id: Optional[str] = Query(None, description="Scope summary to a single run."),
) -> AlertSummary:
    """Return aggregate alert counts (total, by_label, by_severity)."""
    return await _svc.summary(run_id=run_id)


@router.delete("")
async def delete_alerts() -> dict:
    """Purge all alert rows from the database."""
    n = await _svc.clear()
    return {"deleted": n}


@router.delete("/{alert_id}")
async def delete_alert(alert_id: int) -> dict:
    """Delete a single alert row by ID."""
    deleted = await _svc.delete_one(alert_id)
    return {"deleted": deleted, "id": alert_id}
