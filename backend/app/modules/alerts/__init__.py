"""Alerting and notification module for STARF CAN-Bus anomaly detection."""

from functools import lru_cache

from app.modules.alerts.service import (
    AlertCreate,
    AlertNotFoundError,
    AlertRecord,
    AlertService,
    AlertSeverity,
    AlertStats,
    AlertStatus,
    AttackCategory,
    InvalidAlertTransitionError,
    NotificationDispatcher,
)


@lru_cache
def get_alert_service() -> AlertService:
    """Provide a singleton instance of the AlertService."""
    return AlertService()


__all__ = [
    "AlertCreate",
    "AlertNotFoundError",
    "AlertRecord",
    "AlertService",
    "AlertSeverity",
    "AlertStats",
    "AlertStatus",
    "AttackCategory",
    "InvalidAlertTransitionError",
    "NotificationDispatcher",
    "get_alert_service",
]
