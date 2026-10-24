"""Model evaluation, performance metrics, and reporting for STARK."""

from stark.eval.metrics import (
    compute_accuracy,
    compute_classification_metrics,
    compute_confusion_matrix,
    compute_rates,
)
from stark.eval.report import generate_metrics_report

__all__ = [
    "compute_accuracy",
    "compute_classification_metrics",
    "compute_confusion_matrix",
    "compute_rates",
    "generate_metrics_report",
]
