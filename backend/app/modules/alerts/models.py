"""SQLAlchemy 2.0 ORM model for the ``alerts`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Alert(Base):
    """Persisted alert record produced by the hybrid fusion pipeline.

    Columns
    -------
    id            : integer primary key (auto-increment).
    run_id        : string identifier for the detection run that produced this alert.
    created_at    : UTC timestamp of record insertion (server default: now).
    timestamp     : CAN frame capture time (seconds, float).
    can_id        : raw integer CAN arbitration ID.
    label         : fusion decision label (e.g. 'dos', 'ATTACK (unclassified)').
    confidence    : fusion decision confidence in [0.0, 1.0].
    stage         : pipeline stage string ('both', 'stage1', 'stage2', 'stage1_persistent').
    severity_level: categorical severity tier ('NONE', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL').
    severity_score: integer severity points (0–12).
    rule_ids      : comma-separated list of fired Stage 1 rule IDs (e.g. 'R1,R3').
    reason        : human-readable diagnostic rationale.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    can_id: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    severity_level: Mapped[str] = mapped_column(String, nullable=False)
    severity_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rule_ids: Mapped[str] = mapped_column(String, nullable=False, default="")
    reason: Mapped[str] = mapped_column(String, nullable=False, default="")
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (Index("ix_alerts_run_id_severity", "run_id", "severity_level"),)
