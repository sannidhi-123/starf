"""AlertService: async CRUD operations for Alert records.

All methods accept an optional ``session`` keyword argument so they can
participate in an external transaction during testing.  When not supplied,
the service opens its own session via ``SessionLocal``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.modules.alerts.models import Alert
from app.modules.alerts.schemas import AlertOut, AlertSummary


class AlertService:
    """Application service for persisting and querying Alert records."""

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    async def add_many(self, run_id: str, alerts: list[dict[str, Any]]) -> int:
        """Bulk-insert alert dicts for *run_id* and return the inserted count.

        Each dict may contain any subset of Alert columns; ``run_id`` and
        ``created_at`` are always set by this method.
        """
        if not alerts:
            return 0

        now = datetime.now(timezone.utc)
        rows: list[Alert] = []
        for raw in alerts:
            rows.append(
                Alert(
                    run_id=run_id,
                    created_at=now,
                    timestamp=float(raw.get("timestamp", 0.0)),
                    can_id=int(raw.get("can_id", 0)),
                    label=str(raw.get("label", "normal")),
                    confidence=float(raw.get("confidence", 0.0)),
                    stage=str(raw.get("stage", "stage1")),
                    severity_level=str(raw.get("severity_level", "NONE")),
                    severity_score=int(raw.get("severity_score", 0)),
                    rule_ids=str(raw.get("rule_ids", "")),
                    reason=str(raw.get("reason", "")),
                )
            )

        async with SessionLocal() as session:
            session.add_all(rows)
            await session.commit()

        return len(rows)

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    async def list_alerts(
        self,
        run_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> list[AlertOut]:
        """Return alerts, optionally filtered by *run_id* and/or *severity_level*.

        Results are ordered by ``id`` descending (most recent first) and
        capped at *limit* rows.
        """
        stmt = select(Alert).order_by(Alert.id.desc()).limit(limit)
        if run_id is not None:
            stmt = stmt.where(Alert.run_id == run_id)
        if severity is not None:
            stmt = stmt.where(Alert.severity_level == severity)

        async with SessionLocal() as session:
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [AlertOut.model_validate(row) for row in rows]

    async def summary(self, run_id: Optional[str] = None) -> AlertSummary:
        """Return aggregated counts (total, by_label, by_severity) for *run_id*.

        If *run_id* is None the summary spans all runs.
        """
        # Build the base filter condition once
        async with SessionLocal() as session:
            # Total count
            total_stmt = select(func.count()).select_from(Alert)
            if run_id is not None:
                total_stmt = total_stmt.where(Alert.run_id == run_id)
            total: int = (await session.execute(total_stmt)).scalar_one()

            # Count by label
            label_stmt = select(Alert.label, func.count().label("cnt")).group_by(Alert.label)
            if run_id is not None:
                label_stmt = label_stmt.where(Alert.run_id == run_id)
            label_rows = (await session.execute(label_stmt)).all()

            # Count by severity_level
            sev_stmt = select(Alert.severity_level, func.count().label("cnt")).group_by(
                Alert.severity_level
            )
            if run_id is not None:
                sev_stmt = sev_stmt.where(Alert.run_id == run_id)
            sev_rows = (await session.execute(sev_stmt)).all()

        by_label: dict[str, int] = {row.label: row.cnt for row in label_rows}
        by_severity: dict[str, int] = {row.severity_level: row.cnt for row in sev_rows}

        return AlertSummary(total=total, by_label=by_label, by_severity=by_severity)

    # ------------------------------------------------------------------
    # Delete helpers
    # ------------------------------------------------------------------

    async def delete_one(self, alert_id: int) -> bool:
        """Delete a single alert by ID. Returns True if found and deleted."""
        async with SessionLocal() as session:
            result = await session.execute(delete(Alert).where(Alert.id == alert_id))
            await session.commit()
        return bool(result.rowcount and result.rowcount > 0)

    async def clear(self) -> int:
        """Delete **all** alert rows.  Returns the number of rows deleted."""
        async with SessionLocal() as session:
            result = await session.execute(delete(Alert))
            await session.commit()
        return result.rowcount  # type: ignore[return-value]
