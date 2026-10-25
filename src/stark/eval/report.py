"""Metrics reporting and JSON serialization for STARK model evaluations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from stark.config import REPORTS_DIR
from stark.utils.logging import get_logger

logger = get_logger(__name__)


def generate_metrics_report(
    dataset_name: str,
    split_sizes: dict[str, int],
    model_version: str,
    metrics: dict[str, Any],
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Generate and write a comprehensive JSON evaluation metrics report.

    Args:
        dataset_name: Name of the evaluated dataset.
        split_sizes: Dictionary mapping split names (train, val, test) to row counts.
        model_version: Model identifier or version string.
        metrics: Dictionary of evaluated metrics produced by compute_classification_metrics().
        output_path: Destination JSON path (defaults to reports/metrics.json).

    Returns:
        dict[str, Any]: The complete serialized report dictionary.
    """
    path = (
        Path(output_path) if output_path is not None else (REPORTS_DIR / "metrics.json")
    )
    path.parent.mkdir(parents=True, exist_ok=True)

    report_payload: dict[str, Any] = {
        "dataset_name": dataset_name,
        "model_version": model_version,
        "split_sizes": dict(split_sizes),
        "metrics": metrics,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    with path.open("w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

    logger.info("Wrote evaluation metrics report to: %s", path)
    return report_payload
