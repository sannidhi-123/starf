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

router = APIRouter()


@router.get("", response_model=dict[str, Any])
@router.get("/", response_model=dict[str, Any])
async def list_alerts(
    severity: Optional[str] = Query(default=None, description="Filter by severity (low, medium, high, critical)"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by status (active, acknowledged, resolved)"),
    attack_category: Optional[str] = Query(default=None, description="Filter by attack category"),
    can_id: Optional[str] = Query(default=None, description="Filter by CAN arbitration ID"),
    limit: int = Query(default=100, ge=1, le=500, description="Max alerts to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    service: AlertService = Depends(get_alert_service),
    integration: Integration = Depends(get_integration),
) -> dict[str, Any]:
    """Retrieve filtered security alerts from the STARF detection pipeline."""
    alerts = service.list_alerts(
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


@router.post("", response_model=AlertRecord, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=AlertRecord, status_code=status.HTTP_201_CREATED)
def create_alert(
    payload: AlertCreate,
    service: AlertService = Depends(get_alert_service),
) -> AlertRecord:
    """Record a newly generated security alert from detection rules or ML models."""
    return service.create_alert(payload)


@router.get("/stats", response_model=AlertStats)
def get_alert_stats(
    service: AlertService = Depends(get_alert_service),
) -> AlertStats:
    """Retrieve aggregate counts across severities and alert lifecycles."""
    return service.get_stats()


@router.get("/{alert_id}", response_model=AlertRecord)
def get_alert(
    alert_id: str,
    service: AlertService = Depends(get_alert_service),
) -> AlertRecord:
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
