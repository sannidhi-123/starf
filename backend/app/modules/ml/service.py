"""MLService: models, architectures, and telemetry metadata for STARF."""

from __future__ import annotations

from typing import Any, Dict, List


class MLService:
    """Service providing metadata and status for STARF ML pipeline stages."""

    def get_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "stage1_rule_engine",
                "name": "Stage 1 Rule Engine & Baseline Profiler",
                "stage": "Stage 1",
                "type": "Deterministic Protocol Filter",
                "version": "1.0.0",
                "status": "active",
                "status_label": "Production Tuned",
                "description": "Applies 7 physical & statistical CAN rules (R1–R7) to filter 98%+ of normal frames with sub-millisecond overhead.",
                "rules": [
                    {"id": "R1", "name": "Unauthorized CAN ID", "weight": 3, "level": "VIOLATION"},
                    {"id": "R2", "name": "Impossible Inter-Arrival Δt Floor", "weight": 3, "level": "VIOLATION"},
                    {"id": "R3", "name": "Bus Flooding Rate Violation", "weight": 2, "level": "SUSPECT"},
                    {"id": "R4", "name": "DLC Payload Length Mismatch", "weight": 3, "level": "VIOLATION"},
                    {"id": "R5", "name": "Identical Payload Repetition Burst", "weight": 2, "level": "SUSPECT"},
                    {"id": "R6", "name": "Aperiodic Payload Variation Anomaly", "weight": 2, "level": "SUSPECT"},
                    {"id": "R7", "name": "Message Silence Watchdog Timeout", "weight": 1, "level": "INFO"},
                ],
                "metrics": {
                    "fpr": "1.31%",
                    "filter_rate": "98.69%",
                    "median_latency": "0.015 ms/frame",
                },
            },
            {
                "id": "stage2_classifier",
                "name": "Stage 2 Multi-Class Anomaly Classifier",
                "stage": "Stage 2",
                "type": "LightGBM Gradient-Boosted Classifier",
                "version": "0.2.0-stub",
                "status": "stub",
                "status_label": "Deterministic Demo Stub",
                "description": "Evaluates suspicious CAN frames with normalized multi-class probabilities across 4 attack categories.",
                "classes": ["normal", "dos", "fuzzy", "spoofing"],
                "features": [
                    "dt_same_id (Inter-arrival Δt per arbitration ID)",
                    "msg_rate_50ms (Sliding 50ms window frame count)",
                    "payload_hamming_distance (Bitwise XOR byte transitions)",
                    "byte_entropy (Shannon payload entropy)",
                    "can_id (Normalized arbitration ID)",
                ],
                "metrics": {
                    "input_dim": 5,
                    "target_accuracy": "99.4%",
                    "integration_phase": "Day 15 Demo Sprint (Full LightGBM swap planned Day 16)",
                },
            },
            {
                "id": "stage3_hybrid_fusion",
                "name": "Stage 3 Hybrid Fusion & Severity Engine",
                "stage": "Stage 3",
                "type": "7-Row Deterministic Arbitration Matrix",
                "version": "1.0.0",
                "status": "active",
                "status_label": "Production Active",
                "description": "Arbitrates deterministic rule violations and ML statistical predictions into a unified decision with 0–100 severity scoring.",
                "matrix_rows": 7,
                "severity_levels": [
                    {"level": "CRITICAL", "range": "85–100", "description": "Dual-confirmed attack or high-weight violation with high confidence"},
                    {"level": "HIGH", "range": "60–84", "description": "Confirmed attack or high-weight violation with moderate confidence"},
                    {"level": "MEDIUM", "range": "30–59", "description": "Corroborated suspect or ML attack without Stage 1 violation (capped at 55)"},
                    {"level": "LOW", "range": "0–29", "description": "Normal or low-confidence anomaly"},
                ],
                "metrics": {
                    "arbitration_budget": "< 0.005 ms",
                    "override_policy": "Stage 1 VIOLATION claims priority on conflict",
                },
            },
        ]
