"""Train a baseline classifier on STARK features and write an evaluation report."""

from __future__ import annotations

import time

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from stark.config import PROCESSED_DATA_DIR, REPORTS_DIR
from stark.eval.metrics import compute_classification_metrics
from stark.eval.report import generate_metrics_report

FEATURES_DIR = PROCESSED_DATA_DIR / "features"
SEED = 42


def load(split: str) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.load(FEATURES_DIR / f"X_{split}.npy"),
        np.load(FEATURES_DIR / f"y_{split}.npy"),
    )


def measure_latency_ms(model, X: np.ndarray, n: int = 1000, warmup: int = 100) -> list[float]:
    """Time single-row predictions, excluding warm-up calls."""
    rng = np.random.default_rng(SEED)
    rows = X[rng.integers(0, len(X), size=n + warmup)]
    times: list[float] = []
    for i, row in enumerate(rows):
        start = time.perf_counter()
        model.predict(row.reshape(1, -1))
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if i >= warmup:
            times.append(elapsed_ms)
    return times


def main() -> None:
    X_train, y_train = load("train")
    X_val, y_val = load("val")
    X_test, y_test = load("test")

    model = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=SEED,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    # Validation is for tuning only. Test is touched once, below.
    val_acc = float(np.mean(model.predict(X_val) == y_val))
    print(f"validation accuracy: {val_acc:.4f}")

    y_pred = model.predict(X_test)
    latencies = measure_latency_ms(model, X_test)
    metrics = compute_classification_metrics(y_test, y_pred, latencies=latencies)

    # Reference point: a model that always predicts normal (label 0).
    baseline_pred = np.zeros_like(y_test)
    metrics["all_normal_baseline_accuracy"] = round(float(np.mean(baseline_pred == y_test)), 6)

    # Sanity check: per-class support must cover the whole test set.
    total_support = sum(int(v["support"]) for v in metrics["per_class"].values())
    assert total_support == len(y_test), (
        f"per-class support {total_support} != test size {len(y_test)}"
    )

    generate_metrics_report(
        dataset_name="fixture (synthetic)",
        split_sizes={"train": len(y_train), "val": len(y_val), "test": len(y_test)},
        model_version="rf_baseline_v1",
        metrics=metrics,
        output_path=REPORTS_DIR / "metrics_rf_baseline.json",
    )
    print("accuracy:", metrics["accuracy"], "macro_f1:", metrics["macro_f1"])
    print("fpr/fnr:", metrics["fpr"], metrics["fnr"])
    print("median latency ms:", metrics["median_latency_ms"])
    print("confusion matrix:", metrics["confusion_matrix"])
    print("all-normal baseline accuracy:", metrics["all_normal_baseline_accuracy"])


if __name__ == "__main__":
    main()