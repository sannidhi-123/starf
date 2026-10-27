"""Pydantic schemas for the Alerts API.

AlertOut     – full column representation of a persisted Alert row, with an
               extra computed field ``can_id_hex`` (e.g. "0x0140").
AlertSummary – aggregate counts for dashboard tiles.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, computed_field


class AlertOut(BaseModel):
    """Serialisation schema for a single Alert DB row."""

    id: int
    run_id: str
    created_at: datetime
    timestamp: float
    can_id: int
    label: str
    confidence: float
    stage: str
    severity_level: str
    severity_score: int
    rule_ids: str
    reason: str
    details: dict = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def can_id_hex(self) -> str:
        """Return CAN ID as a zero-padded 4-digit hex string, e.g. '0x0140'."""
        return f"0x{self.can_id:04X}"

    model_config = {"from_attributes": True}


class AlertSummary(BaseModel):
    """Aggregated alert statistics for a run or across all runs."""

    total: int = Field(0, description="Total number of alerts.")
    by_label: dict[str, int] = Field(
        default_factory=dict, description="Alert count keyed by decision label."
    )
    by_severity: dict[str, int] = Field(
        default_factory=dict, description="Alert count keyed by severity level."
    )
