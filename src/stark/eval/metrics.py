"""Classification and intrusion detection evaluation metrics for STARK.

Supports binary and multi-class label arrays, operating independently of the
underlying model architecture (can run on mock predictions, ground truth,
or Stage 1/Stage 2 model outputs).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


def compute_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute standard classification accuracy.

    Formula:
        accuracy = sum(I(y_true == y_pred)) / N

    Args:
        y_true: Ground truth target array.
        y_pred: Predicted label array.

    Returns:
        float: Accuracy score in [0.0, 1.0].
    """
    if len(y_true) == 0:
        return 0.0
    return float(np.mean(y_true == y_pred))


def compute_confusion_matrix(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    labels: Sequence[int] | None = None,
) -> list[list[int]]:
    """Compute confusion matrix for arbitrary integer label arrays.

    For binary classification with labels [0, 1]:
        returns [[TN, FP], [FN, TP]]

    Args:
        y_true: Ground truth target array.
        y_pred: Predicted label array.
        labels: Optional explicit ordering of unique labels.

    Returns:
        list[list[int]]: 2D confusion matrix where row i represents true class
            and column j represents predicted class.
    """
    if labels is None:
        unique_labels = sorted(set(y_true).union(set(y_pred)))
    else:
        unique_labels = list(labels)

    if not unique_labels:
        return []

    label_to_idx = {val: idx for idx, val in enumerate(unique_labels)}
    n_classes = len(unique_labels)
    matrix = np.zeros((n_classes, n_classes), dtype=int)

    for yt, yp in zip(y_true, y_pred):
        if yt in label_to_idx and yp in label_to_idx:
            matrix[label_to_idx[yt]][label_to_idx[yp]] += 1

    return matrix.tolist()


def compute_rates(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    """Compute False Positive Rate (FPR) and False Negative Rate (FNR).

    In CAN security detection, 0 represents normal traffic and any non-zero
    label represents an attack or anomaly.

    Formulas:
        FPR = FP / (FP + TN)
        FNR = FN / (FN + TP)

    Args:
        y_true: Ground truth target array.
        y_pred: Predicted label array.

    Returns:
        tuple[float, float]: (fpr, fnr) in [0.0, 1.0].
    """
    y_true_arr = np.asarray(y_true)
    y_pred_arr = np.asarray(y_pred)

    normal_mask = y_true_arr == 0
    attack_mask = y_true_arr != 0

    tn = int(np.sum((y_pred_arr == 0) & normal_mask))
    fp = int(np.sum((y_pred_arr != 0) & normal_mask))
    fn = int(np.sum((y_pred_arr == 0) & attack_mask))
    tp = int(np.sum((y_pred_arr != 0) & attack_mask))

    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    fnr = float(fn / (fn + tp)) if (fn + tp) > 0 else 0.0

    return fpr, fnr


def compute_per_class_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    labels: Sequence[int] | None = None,
) -> dict[str, dict[str, float]]:
    """Compute precision, recall, and F1 score per class.

    Args:
        y_true: Ground truth target array.
        y_pred: Predicted label array.
        labels: Optional sequence of unique class labels.

    Returns:
        dict[str, dict[str, float]]: Dictionary mapping class name/id to metrics:
            precision, recall, f1, support.
    """
    y_true_arr = np.asarray(y_true)
    y_pred_arr = np.asarray(y_pred)

    if labels is None:
        unique_labels = sorted(set(y_true_arr).union(set(y_pred_arr)))
    else:
        unique_labels = list(labels)

    per_class: dict[str, dict[str, float]] = {}

    for cls_val in unique_labels:
        tp = int(np.sum((y_pred_arr == cls_val) & (y_true_arr == cls_val)))
        fp = int(np.sum((y_pred_arr == cls_val) & (y_true_arr != cls_val)))
        fn = int(np.sum((y_pred_arr != cls_val) & (y_true_arr == cls_val)))
        support = int(np.sum(y_true_arr == cls_val))

        precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (
            float(2 * precision * recall / (precision + recall))
            if (precision + recall) > 0
            else 0.0
        )

        per_class[str(cls_val)] = {
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
            "support": float(support),
        }

    return per_class


def compute_classification_metrics(
    y_true: Sequence[int] | np.ndarray,
    y_pred: Sequence[int] | np.ndarray,
    latencies: Sequence[float] | np.ndarray | None = None,
) -> dict[str, Any]:
    """Compute comprehensive classification performance metrics.

    Calculates:
    - accuracy
    - macro precision, macro recall, macro F1
    - per-class precision, recall, F1, support
    - confusion matrix
    - False Positive Rate (FPR)
    - False Negative Rate (FNR)
    - median latency (ms)

    Args:
        y_true: Ground truth label array.
        y_pred: Predicted label array.
        latencies: Optional sequence of per-frame inference latencies in seconds or ms.

    Returns:
        dict[str, Any]: Dictionary containing all computed metric figures.
    """
    yt = np.asarray(y_true)
    yp = np.asarray(y_pred)

    if len(yt) == 0:
        return {
            "accuracy": 0.0,
            "macro_precision": 0.0,
            "macro_recall": 0.0,
            "macro_f1": 0.0,
            "fpr": 0.0,
            "fnr": 0.0,
            "median_latency_ms": 0.0,
            "per_class": {},
            "confusion_matrix": [],
        }

    accuracy = compute_accuracy(yt, yp)
    per_class = compute_per_class_metrics(yt, yp)
    conf_matrix = compute_confusion_matrix(yt, yp)
    fpr, fnr = compute_rates(yt, yp)

    if per_class:
        macro_prec = float(np.mean([m["precision"] for m in per_class.values()]))
        macro_rec = float(np.mean([m["recall"] for m in per_class.values()]))
        macro_f1 = float(np.mean([m["f1"] for m in per_class.values()]))
    else:
        macro_prec, macro_rec, macro_f1 = 0.0, 0.0, 0.0

    if latencies is not None and len(latencies) > 0:
        median_lat = float(np.median(latencies))
    else:
        median_lat = 0.0

    return {
        "accuracy": round(accuracy, 6),
        "macro_precision": round(macro_prec, 6),
        "macro_recall": round(macro_rec, 6),
        "macro_f1": round(macro_f1, 6),
        "fpr": round(fpr, 6),
        "fnr": round(fnr, 6),
        "median_latency_ms": round(median_lat, 4),
        "per_class": per_class,
        "confusion_matrix": conf_matrix,
    }
