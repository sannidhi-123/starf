"""Alerts API routes for STARF.

Provides:
- GET    /api/v1/alerts                  List alerts (filters: run_id, severity, status, attack_category, can_id).
- GET    /api/v1/alerts/summary          Aggregate counts for detection dashboard (total, by_label, by_severity).
- GET    /api/v1/alerts/stats            Aggregate counts across severities and alert lifecycles.
- POST   /api/v1/alerts                  Record a newly generated security alert.
- GET    /api/v1/alerts/{alert_id}       Retrieve full incident details for a single alert.
- POST   /api/v1/alerts/{alert_id}/acknowledge  Acknowledge an active alert.
- POST   /api/v1/alerts/{alert_id}/resolve      Resolve an alert.
- DELETE /api/v1/alerts                  Purge all alerts.
- DELETE /api/v1/alerts/{alert_id}       Delete single alert by ID.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import get_integration
from app.integrations.base import Integration
from app.modules.alerts import (
    AlertCreate,
    AlertNotFoundError,
    AlertRecord,
    AlertService,
    AlertStats,
    InvalidAlertTransitionError,
    get_alert_service,
)
from app.modules.alerts.schemas import AlertSummary

router = APIRouter()


@router.get("", response_model=dict[str, Any])
@router.get("/", response_model=dict[str, Any])
async def list_alerts(
    run_id: Optional[str] = Query(
        default=None, description="Filter by detection run ID."
    ),
    severity: Optional[str] = Query(
        default=None, description="Filter by severity level."
    ),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status (active, acknowledged, resolved)",
    ),
    attack_category: Optional[str] = Query(
        default=None, description="Filter by attack category"
    ),
    can_id: Optional[str] = Query(
        default=None, description="Filter by CAN arbitration ID"
    ),
    limit: int = Query(
        default=100, ge=1, le=10_000, description="Max alerts to return"
    ),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    service: AlertService = Depends(get_alert_service),
    integration: Integration = Depends(get_integration),
) -> dict[str, Any]:
    """Retrieve filtered security alerts from the STARF detection pipeline."""
    alerts = await service.list_alerts(
        run_id=run_id,
        severity=severity,
        status=status_filter,
        attack_category=attack_category,
        can_id=can_id,
        limit=limit,
        offset=offset,
    )
    items = [a.model_dump(mode="json") for a in alerts]

    # Integrate external/mock alerts if available and not duplicated
    try:
        external_alerts = await integration.list_alerts()
        known_ids = {i["id"] for i in items if "id" in i}
        for ext in external_alerts:
            if isinstance(ext, dict) and ext.get("id") not in known_ids:
                items.append(ext)
    except Exception:
        pass

    return {
        "items": items,
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


@router.get("/summary", response_model=AlertSummary)
async def alert_summary(
    run_id: Optional[str] = Query(None, description="Scope summary to a single run."),
    service: AlertService = Depends(get_alert_service),
) -> AlertSummary:
    """Return aggregate alert counts (total, by_label, by_severity)."""
    return await service.summary(run_id=run_id)


@router.get("/stats", response_model=AlertStats)
def get_alert_stats(
    service: AlertService = Depends(get_alert_service),
) -> AlertStats:
    """Retrieve aggregate counts across severities and alert lifecycles."""
    return service.get_stats()


@router.post("", response_model=AlertRecord, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=AlertRecord, status_code=status.HTTP_201_CREATED)
def create_alert(
    payload: AlertCreate,
    service: AlertService = Depends(get_alert_service),
) -> AlertRecord:
    """Record a newly generated security alert from detection rules or ML models."""
    return service.create_alert(payload)


@router.get("/{alert_id}", response_model=Any)
def get_alert(
    alert_id: str,
    service: AlertService = Depends(get_alert_service),
) -> Any:
    """Retrieve full incident details for a single alert."""
    try:
        return service.get_alert(alert_id)
    except AlertNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/{alert_id}/acknowledge", response_model=AlertRecord)
def acknowledge_alert(
    alert_id: str,
    service: AlertService = Depends(get_alert_service),
) -> AlertRecord:
    """Acknowledge an active alert, marking operator incident review."""
    try:
        return service.acknowledge_alert(alert_id)
    except AlertNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except InvalidAlertTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/{alert_id}/resolve", response_model=AlertRecord)
def resolve_alert(
    alert_id: str,
    service: AlertService = Depends(get_alert_service),
) -> AlertRecord:
    """Resolve an incident alert."""
    try:
        return service.resolve_alert(alert_id)
    except AlertNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.delete("")
@router.delete("/")
async def delete_alerts(
    service: AlertService = Depends(get_alert_service),
) -> dict[str, Any]:
    """Purge all alert rows from the database."""
    n = await service.clear()
    return {"deleted": n}


@router.delete("/{alert_id}")
async def delete_alert(
    alert_id: str,
    service: AlertService = Depends(get_alert_service),
) -> dict[str, Any]:
    """Delete a single alert row by ID."""
    deleted = await service.delete_one(alert_id)
    return {"deleted": deleted, "id": alert_id}
