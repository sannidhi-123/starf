"""Train and evaluate the standard time-ordered random-forest split."""

from __future__ import annotations

import argparse
import json
import time
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from stark.config import PROCESSED_DATA_DIR, REPORTS_DIR
from stark.eval.metrics import compute_classification_metrics
from stark.eval.resampling import prepare_train_validation_test

FEATURES_DIR = PROCESSED_DATA_DIR / "features"
DEFAULT_SEED = 42


def load(split: str) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.load(FEATURES_DIR / f"X_{split}.npy"),
        np.load(FEATURES_DIR / f"y_{split}.npy"),
    )


def class_counts(labels: np.ndarray) -> dict[str, int]:
    return {
        str(label): int(count)
        for label, count in sorted(Counter(map(int, labels)).items())
    }


def _predict_labels(model: RandomForestClassifier, X: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"`sklearn.utils.parallel.delayed` should be used with",
            category=UserWarning,
            module=r"sklearn.utils.parallel",
        )
        return model.predict(X)


def measure_latency_ms(
    model: RandomForestClassifier,
    X: np.ndarray,
    *,
    seed: int,
    n_predictions: int = 1000,
    warmup_calls: int = 100,
) -> dict[str, Any]:
    """Measure 1,000 single-row predict calls after warm-up; feature extraction is excluded."""
    if len(X) == 0:
        raise ValueError("Cannot measure latency on an empty test split")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(X), size=n_predictions + warmup_calls)
    elapsed_ms: list[float] = []
    for call_index, row_index in enumerate(indices):
        row = X[row_index].reshape(1, -1)
        started = time.perf_counter()
        _predict_labels(model, row)
        duration_ms = (time.perf_counter() - started) * 1000.0
        if call_index >= warmup_calls:
            elapsed_ms.append(duration_ms)

    p50, p95, p99 = np.percentile(elapsed_ms, [50, 95, 99])
    return {
        "timed_operation": "model.predict on one feature row; feature extraction excluded",
        "warmup_calls": warmup_calls,
        "timed_predictions": n_predictions,
        "units": "milliseconds",
        "p50": round(float(p50), 6),
        "p95": round(float(p95), 6),
        "p99": round(float(p99), 6),
    }


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    result = compute_classification_metrics(y_true, y_pred)
    result.pop("median_latency_ms", None)
    result["sample_count"] = len(y_true)
    result["class_counts"] = class_counts(y_true)
    result["all_normal_baseline_accuracy"] = round(
        float(np.mean(y_true == 0)) if len(y_true) else 0.0, 6
    )
    return result


def evaluate(*, use_smote: bool, seed: int) -> dict[str, Any]:
    X_train, y_train = load("train")
    X_val, y_val = load("val")
    X_test, y_test = load("test")
    train_counts_before = class_counts(y_train)
    train_rows_before = len(y_train)

    X_train, y_train, X_val, y_val, X_test, y_test = prepare_train_validation_test(
        X_train,
        y_train,
        X_val,
        y_val,
        X_test,
        y_test,
        use_smote=use_smote,
        random_state=seed,
    )
    train_counts_after = class_counts(y_train)

    model_config = {
        "estimator": "RandomForestClassifier",
        "n_estimators": 100,
        "class_weight": "balanced",
        "random_state": seed,
        "n_jobs": 1,
        "decision_threshold": 0.5,
    }
    model = RandomForestClassifier(
        **{
            key: value
            for key, value in model_config.items()
            if key not in {"estimator", "decision_threshold"}
        }
    )
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"`sklearn.utils.parallel.delayed` should be used with",
            category=UserWarning,
        )
        model.fit(X_train, y_train)

    val_metrics = _metrics(y_val, _predict_labels(model, X_val))
    test_metrics = _metrics(y_test, _predict_labels(model, X_test))
    latency = measure_latency_ms(model, X_test, seed=seed)

    return {
        "dataset_name": "fixture (synthetic, one capture)",
        "seed": seed,
        "smote_used": use_smote,
        "model_configuration": model_config,
        "split_sizes": {
            "train_before_smote": int(train_rows_before),
            "train_after_smote": len(y_train),
            "validation": len(y_val),
            "test": len(y_test),
        },
        "class_counts_per_split": {
            "train_before_smote": train_counts_before,
            "train_after_smote": train_counts_after,
            "validation": class_counts(y_val),
            "test": class_counts(y_test),
        },
        "validation_metrics": val_metrics,
        "test_metrics": test_metrics,
        "latency_percentiles_ms": latency,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smote", action="store_true", help="Apply SMOTE to training data only"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=None, help="JSON output path")
    args = parser.parse_args()

    result = evaluate(use_smote=args.smote, seed=args.seed)
    output_path = args.output or REPORTS_DIR / (
        "standard_split_smote.json" if args.smote else "standard_split_baseline.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"SMOTE: {result['smote_used']}")
    print(
        f"training class counts before: {result['class_counts_per_split']['train_before_smote']}"
    )
    print(
        f"training class counts after:  {result['class_counts_per_split']['train_after_smote']}"
    )
    print(
        "test accuracy:"
        f" {result['test_metrics']['accuracy']:.6f}"
        " (all-normal baseline:"
        f" {result['test_metrics']['all_normal_baseline_accuracy']:.6f};"
        f" n={result['test_metrics']['sample_count']},"
        f" classes={result['test_metrics']['class_counts']})"
    )
    print(f"latency percentiles (ms): {result['latency_percentiles_ms']}")
    print(f"report: {output_path}")


if __name__ == "__main__":
    main()
