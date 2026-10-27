"""MLService: models, architectures, and telemetry metadata for STARF."""

from __future__ import annotations

from typing import Any, Dict, List

import sys
from pathlib import Path


class MLService:
    """Service providing metadata and status for STARF ML pipeline stages."""

    def get_models(self) -> List[Dict[str, Any]]:
        # Resolve the shared src package even when the API is launched from backend/.
        repo_root = Path(__file__).resolve().parents[4]
        src_dir = str(repo_root / "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from stark.ml.predict import model_status

        ml_status = model_status()
        return [
            {
                "id": "stage1_rule_engine",
                "name": "Stage 1 Rule Engine & Baseline Profiler",
                "stage": "Stage 1",
                "type": "Deterministic Protocol Filter",
                "version": "1.0.0",
                "status": "active",
                "status_label": "Rule engine active; thresholds require dataset validation",
                "description": "Applies the configured R1–R7 deterministic CAN checks.",
                "rules": [
                    {
                        "id": "R1",
                        "name": "Unauthorized CAN ID",
                        "weight": 3,
                        "level": "VIOLATION",
                    },
                    {
                        "id": "R2",
                        "name": "Impossible Inter-Arrival Δt Floor",
                        "weight": 3,
                        "level": "VIOLATION",
                    },
                    {
                        "id": "R3",
                        "name": "Bus Flooding Rate Violation",
                        "weight": 2,
                        "level": "SUSPECT",
                    },
                    {
                        "id": "R4",
                        "name": "DLC Payload Length Mismatch",
                        "weight": 3,
                        "level": "VIOLATION",
                    },
                    {
                        "id": "R5",
                        "name": "Identical Payload Repetition Burst",
                        "weight": 2,
                        "level": "SUSPECT",
                    },
                    {
                        "id": "R6",
                        "name": "Aperiodic Payload Variation Anomaly",
                        "weight": 2,
                        "level": "SUSPECT",
                    },
                    {
                        "id": "R7",
                        "name": "Message Silence Watchdog Timeout",
                        "weight": 1,
                        "level": "INFO",
                    },
                ],
                "metrics": {"validation_report": "reports/stage1_only_metrics.json"},
            },
            {
                "id": "stage2_classifier",
                "name": "Stage 2 Optional Classifier",
                "stage": "Stage 2",
                "type": ml_status["model_type"]
                or (
                    "Deterministic Demo Stub"
                    if ml_status["mode"] == "demo"
                    else "Unavailable"
                ),
                "version": "runtime",
                "status": (
                    "active"
                    if ml_status["available"]
                    else ("stub" if ml_status["mode"] == "demo" else "unavailable")
                ),
                "status_label": ml_status["mode"].replace("_", " ").title(),
                "description": "A trained estimator is used only when a compatible artifact loads; otherwise runtime mode is explicit.",
                "classes": ["normal", "dos", "fuzzy", "spoofing", "impersonation"],
                "features": ml_status["features"],
                "metrics": {
                    "input_dim": len(ml_status["features"]),
                    "available": ml_status["available"],
                    "load_error": ml_status["load_error"],
                },
            },
            {
                "id": "stage3_hybrid_fusion",
                "name": "Stage 3 Hybrid Fusion & Severity Engine",
                "stage": "Stage 3",
                "type": "7-Row Deterministic Arbitration Matrix",
                "version": "1.0.0",
                "status": "active",
                "status_label": "Active in the demo pipeline",
                "description": "Combines the configured rule verdict with the selected Stage 2 runtime mode and assigns severity.",
                "matrix_rows": 7,
                "severity_levels": [
                    {
                        "level": "CRITICAL",
                        "range": "85–100",
                        "description": "Dual-confirmed attack or high-weight violation with high confidence",
                    },
                    {
                        "level": "HIGH",
                        "range": "60–84",
                        "description": "Confirmed attack or high-weight violation with moderate confidence",
                    },
                    {
                        "level": "MEDIUM",
                        "range": "30–59",
                        "description": "Corroborated suspect or ML attack without Stage 1 violation (capped at 55)",
                    },
                    {
                        "level": "LOW",
                        "range": "0–29",
                        "description": "Normal or low-confidence anomaly",
                    },
                ],
                "metrics": {
                    "arbitration_budget": "< 0.005 ms",
                    "override_policy": "Stage 1 VIOLATION claims priority on conflict",
                },
            },
        ]
