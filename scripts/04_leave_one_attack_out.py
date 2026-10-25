"""Run per-attack leave-one-out evaluation on the synthetic STARK fixture."""

from __future__ import annotations

import argparse
import json
import warnings
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from stark.config import REPORTS_DIR, SAMPLES_DIR
from stark.eval.resampling import prepare_train_validation_test
from stark.features.build import build_feature_matrix
from stark.features.state import FeatureBaseline
from stark.schema import cast_canonical_df

ATTACKS = ["dos", "fuzzy", "gear_spoof", "rpm_spoof"]
DEFAULT_SEEDS = [42, 7, 123]


def class_counts(labels: np.ndarray) -> dict[str, int]:
    return {
        str(label): int(count)
        for label, count in sorted(Counter(map(int, labels)).items())
    }


def attack_type_counts(frame: pd.DataFrame) -> dict[str, int]:
    counts = Counter(map(str, frame["attack_type"].astype(str)))
    return dict(sorted(counts.items()))


def probability_summary(probabilities: np.ndarray) -> dict[str, Any]:
    quantiles = np.percentile(probabilities, [0, 10, 25, 50, 75, 90, 100])
    return {
        "sample_count": len(probabilities),
        "quantiles": {
            key: round(float(value), 6)
            for key, value in zip(
                ("min", "p10", "p25", "p50", "p75", "p90", "max"), quantiles
            )
        },
        "fraction_within_0_1_of_0_5": round(
            float(np.mean(np.abs(probabilities - 0.5) <= 0.1)), 6
        ),
    }


def binary_rates(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    normal = y_true == 0
    attack = y_true == 1
    tp = int(np.sum(attack & (y_pred == 1)))
    fn = int(np.sum(attack & (y_pred == 0)))
    fp = int(np.sum(normal & (y_pred == 1)))
    tn = int(np.sum(normal & (y_pred == 0)))
    return {
        "sample_count": len(y_true),
        "class_counts": class_counts(y_true),
        "attack_frames": int(np.sum(attack)),
        "normal_frames": int(np.sum(normal)),
        "true_positives": tp,
        "false_negatives": fn,
        "false_positives": fp,
        "true_negatives": tn,
        "detected_rate": round(tp / (tp + fn), 6) if tp + fn else 0.0,
        "false_alarm_rate": round(fp / (fp + tn), 6) if fp + tn else 0.0,
    }


def positive_probabilities(model: RandomForestClassifier, X: np.ndarray) -> np.ndarray:
    class_index = int(np.flatnonzero(model.classes_ == 1)[0])
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"`sklearn.utils.parallel.delayed` should be used with",
            category=UserWarning,
            module=r"sklearn.utils.parallel",
        )
        return model.predict_proba(X)[:, class_index]


def select_threshold(y_val: np.ndarray, positive_prob: np.ndarray) -> dict[str, Any]:
    """Maximize validation recall with FPR no higher than validation FPR at 0.5."""
    normal = y_val == 0
    attack = y_val == 1
    default_pred = positive_prob > 0.5
    default_fpr = float(np.mean(default_pred[normal])) if np.any(normal) else 0.0

    candidates = np.unique(
        np.concatenate(
            (
                np.nextafter(positive_prob, -np.inf),
                np.array([0.5, np.nextafter(1.0, np.inf)]),
            )
        )
    )
    feasible: list[tuple[float, float, float]] = []
    for threshold in candidates:
        prediction = positive_prob > threshold
        fpr = float(np.mean(prediction[normal])) if np.any(normal) else 0.0
        recall = float(np.mean(prediction[attack])) if np.any(attack) else 0.0
        if fpr <= default_fpr + 1e-12:
            feasible.append((recall, -fpr, float(threshold)))
    recall, negative_fpr, threshold = max(feasible)
    tuned_pred = positive_prob > threshold
    return {
        "threshold": threshold,
        "selection_rule": "maximize validation recall subject to validation FPR <= validation FPR at threshold 0.5",
        "validation_at_default_threshold": binary_rates(y_val, default_pred),
        "validation_at_selected_threshold": binary_rates(y_val, tuned_pred),
        "validation_threshold_selection": {
            "validation_sample_count": len(y_val),
            "validation_class_counts": class_counts(y_val),
            "default_threshold": 0.5,
            "selected_recall": recall,
            "selected_false_alarm_rate": -negative_fpr,
        },
    }


def validation_split_by_class(train: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Take the latest 20% of each label/attack block as validation, in time order."""
    fit_parts: list[pd.DataFrame] = []
    val_parts: list[pd.DataFrame] = []
    for _, group in train.groupby(["label", "attack_type"], observed=True, sort=False):
        group = group.sort_values("timestamp", kind="mergesort")
        if len(group) < 2:
            raise ValueError(
                "Each training label/attack block needs at least two rows for validation"
            )
        split_at = min(max(int(len(group) * 0.8), 1), len(group) - 1)
        fit_parts.append(group.iloc[:split_at])
        val_parts.append(group.iloc[split_at:])
    fit_df = pd.concat(fit_parts).sort_values("timestamp", kind="mergesort")
    val_df = pd.concat(val_parts).sort_values("timestamp", kind="mergesort")
    return cast_canonical_df(fit_df), cast_canonical_df(val_df)


def _fit_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    *,
    use_smote: bool,
    seed: int,
) -> tuple[RandomForestClassifier, dict[str, int], dict[str, int]]:
    before = class_counts(y_train)
    empty_X = np.empty((0, X_train.shape[1]), dtype=X_train.dtype)
    empty_y = np.empty((0,), dtype=y_train.dtype)
    X_train, y_train, _, _, _, _ = prepare_train_validation_test(
        X_train,
        y_train,
        empty_X,
        empty_y,
        empty_X,
        empty_y,
        use_smote=use_smote,
        random_state=seed,
    )
    after = class_counts(y_train)
    model = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=seed,
        n_jobs=1,
    )
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"`sklearn.utils.parallel.delayed` should be used with",
            category=UserWarning,
        )
        model.fit(X_train, y_train)
    return model, before, after


def evaluate_fuzzy_threshold(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    use_smote: bool,
    seed: int,
) -> dict[str, Any]:
    fit_df, val_df = validation_split_by_class(train)
    baseline = FeatureBaseline.fit(fit_df[fit_df["label"] == 0])
    X_fit, y_fit, baseline = build_feature_matrix(fit_df, baseline=baseline)
    X_val, y_val, _ = build_feature_matrix(val_df, baseline=baseline)
    X_test, y_test, _ = build_feature_matrix(test, baseline=baseline)
    fit_counts_before = class_counts(y_fit)
    fit_rows_before = len(y_fit)
    X_fit, y_fit, X_val, y_val, X_test, y_test = prepare_train_validation_test(
        X_fit,
        y_fit,
        X_val,
        y_val,
        X_test,
        y_test,
        use_smote=use_smote,
        random_state=seed,
    )
    fit_counts_after = class_counts(y_fit)
    model = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=seed,
        n_jobs=1,
    )
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"`sklearn.utils.parallel.delayed` should be used with",
            category=UserWarning,
        )
        model.fit(X_fit, y_fit)
    val_prob = positive_probabilities(model, X_val)
    threshold_data = select_threshold(y_val, val_prob)
    test_prob = positive_probabilities(model, X_test)
    selected_threshold = float(threshold_data["threshold"])
    threshold_data.update(
        {
            "fit_split_rows_before_smote": fit_rows_before,
            "fit_attack_type_counts": attack_type_counts(fit_df),
            "validation_attack_type_counts": attack_type_counts(val_df),
            "fit_class_counts_before_smote": fit_counts_before,
            "fit_class_counts_after_smote": fit_counts_after,
            "test_at_default_threshold": binary_rates(y_test, test_prob > 0.5),
            "test_at_selected_threshold": binary_rates(
                y_test, test_prob > selected_threshold
            ),
            "held_out_fuzzy_probability_summary": probability_summary(
                test_prob[y_test == 1]
            ),
        }
    )
    return threshold_data


def evaluate_fold(
    df: pd.DataFrame,
    held_out_attack: str,
    *,
    use_smote: bool,
    seed: int,
) -> dict[str, Any]:
    normal = df[df["label"] == 0].sort_values("timestamp", kind="mergesort")
    attacks = df[df["label"] == 1]
    normal_cut = int(len(normal) * 0.7)
    normal_train, normal_test = normal.iloc[:normal_cut], normal.iloc[normal_cut:]
    attack_train = attacks[attacks["attack_type"] != held_out_attack]
    attack_test = attacks[attacks["attack_type"] == held_out_attack]
    train = cast_canonical_df(
        pd.concat([normal_train, attack_train]).sort_values(
            "timestamp", kind="mergesort"
        )
    )
    test = cast_canonical_df(
        pd.concat([normal_test, attack_test]).sort_values("timestamp", kind="mergesort")
    )

    baseline = FeatureBaseline.fit(train[train["label"] == 0])
    X_train, y_train, baseline = build_feature_matrix(train, baseline=baseline)
    X_test, y_test, _ = build_feature_matrix(test, baseline=baseline)
    model, train_counts_before, train_counts_after = _fit_model(
        X_train, y_train, use_smote=use_smote, seed=seed
    )
    test_prob = positive_probabilities(model, X_test)
    test_metrics = binary_rates(y_test, test_prob > 0.5)
    result: dict[str, Any] = {
        "seed": seed,
        "training_rows": len(train),
        "training_attack_type_counts": attack_type_counts(train),
        "training_class_counts_before_smote": train_counts_before,
        "training_rows_after_smote": int(sum(train_counts_after.values())),
        "training_class_counts_after_smote": train_counts_after,
        "test_attack_type_counts": attack_type_counts(test),
        "test_metrics_at_threshold_0_5": test_metrics,
    }
    if held_out_attack == "fuzzy":
        result["held_out_fuzzy_probability_summary"] = probability_summary(
            test_prob[y_test == 1]
        )
        result["validation_threshold_analysis"] = evaluate_fuzzy_threshold(
            train, test, use_smote=use_smote, seed=seed
        )
    return result


def evaluate_configuration(
    df: pd.DataFrame,
    *,
    use_smote: bool,
    seeds: list[int],
) -> dict[str, Any]:
    results_by_seed: dict[str, dict[str, Any]] = {}
    for seed in seeds:
        results_by_seed[str(seed)] = {
            attack: evaluate_fold(df, attack, use_smote=use_smote, seed=seed)
            for attack in ATTACKS
        }

    aggregates: dict[str, dict[str, Any]] = {}
    for attack in ATTACKS:
        rows = [
            results_by_seed[str(seed)][attack]["test_metrics_at_threshold_0_5"]
            for seed in seeds
        ]
        detected = np.array([row["detected_rate"] for row in rows])
        false_alarm = np.array([row["false_alarm_rate"] for row in rows])
        aggregates[attack] = {
            "seed_count": len(seeds),
            "seeds": seeds,
            "held_out_attack_frames_per_seed": rows[0]["attack_frames"],
            "normal_test_frames_per_seed": rows[0]["normal_frames"],
            "detected_rate_mean": round(float(detected.mean()), 6),
            "detected_rate_min": round(float(detected.min()), 6),
            "detected_rate_max": round(float(detected.max()), 6),
            "detected_rate_range": round(float(detected.max() - detected.min()), 6),
            "false_alarm_rate_mean": round(float(false_alarm.mean()), 6),
            "false_alarm_rate_min": round(float(false_alarm.min()), 6),
            "false_alarm_rate_max": round(float(false_alarm.max()), 6),
        }

    return {
        "smote_used": use_smote,
        "seeds": seeds,
        "threshold_status": "invalid_method",
        "threshold_note": (
            "Threshold selected on validation data containing only training "
            "attack types, so it does not measure unseen-attack detection. "
            "Do not use."
        ),
        "model_configuration": {
            "estimator": "RandomForestClassifier",
            "n_estimators": 100,
            "class_weight": "balanced",
            "random_state": "per-seed",
            "n_jobs": 1,
            "decision_threshold": 0.5,
        },
        "results_by_seed": results_by_seed,
        "aggregates_by_attack": aggregates,
    }


def merge_configuration(
    path: Path, config_key: str, configuration: dict[str, Any]
) -> None:
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("dataset_name") != "fixture (synthetic, one capture)":
            raise ValueError(f"Refusing to merge into unexpected report: {path}")
    else:
        payload = {
            "dataset_name": "fixture (synthetic, one capture)",
            "split_definition": {
                "normal_training_fraction": 0.7,
                "normal_test_fraction": 0.3,
                "held_out_attack_frames": "all frames from the held-out attack type",
            },
            "configurations": {},
        }
    payload.setdefault("configurations", {})[config_key] = configuration
    payload["generated_at"] = datetime.now(UTC).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smote",
        action="store_true",
        help="Apply SMOTE to each fold's training set only",
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=DEFAULT_SEEDS)
    parser.add_argument(
        "--output", type=Path, default=REPORTS_DIR / "loao_results.json"
    )
    args = parser.parse_args()

    frame = cast_canonical_df(pd.read_csv(SAMPLES_DIR / "fixture.csv"))
    config_key = "smote_on" if args.smote else "smote_off"
    configuration = evaluate_configuration(
        frame, use_smote=args.smote, seeds=args.seeds
    )
    merge_configuration(args.output, config_key, configuration)

    for attack, summary in configuration["aggregates_by_attack"].items():
        print(
            f"{config_key} {attack}: detected mean={summary['detected_rate_mean']:.3f}"
            f" range=[{summary['detected_rate_min']:.3f}, {summary['detected_rate_max']:.3f}]"
            f" from {summary['held_out_attack_frames_per_seed']} attack and"
            f" {summary['normal_test_frames_per_seed']} normal frames/seed;"
            f" false alarm mean={summary['false_alarm_rate_mean']:.3f}"
        )
    print(f"report updated: {args.output}")


if __name__ == "__main__":
    main()
