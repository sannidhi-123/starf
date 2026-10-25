"""Normal-only anomaly detection, leave-one-attack-out.

Train on normal traffic only, so no attack type is seen during training.
The alarm threshold comes from held-out normal frames, never from attack data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from stark.features.build import build_feature_matrix
from stark.schema import cast_canonical_df

SEEDS = [42, 7, 123]
ATTACKS = ["dos", "fuzzy", "gear_spoof", "rpm_spoof"]
OUT = Path("reports/normal_only_results.json")
CALIBRATION_QUANTILE = 0.99


def run_fold(
    normal_train: pd.DataFrame,
    normal_test: pd.DataFrame,
    attacks: pd.DataFrame,
    held_out: str,
    seed: int,
) -> dict[str, Any]:
    # Fit on the first 80% of training normals, calibrate on the last 20%.
    fit_end = int(len(normal_train) * 0.8)
    fit_part = normal_train.iloc[:fit_end]
    calib_part = normal_train.iloc[fit_end:]

    X_fit, _, baseline = build_feature_matrix(fit_part)
    X_cal, _, _ = build_feature_matrix(calib_part, baseline=baseline)

    atk_test = attacks[attacks["attack_type"] == held_out]
    test = pd.concat([normal_test, atk_test]).sort_values("timestamp")
    X_te, y_te, _ = build_feature_matrix(test, baseline=baseline)

    model = IsolationForest(n_estimators=100, random_state=seed, n_jobs=1)
    model.fit(X_fit)

    # Higher score means more anomalous.
    cal_scores = -model.score_samples(X_cal)
    threshold = float(np.quantile(cal_scores, CALIBRATION_QUANTILE))
    scores = -model.score_samples(X_te)
    alarm = scores > threshold

    return {
        "seed": seed,
        "threshold": round(threshold, 6),
        "attack_frames": int((y_te == 1).sum()),
        "normal_frames": int((y_te == 0).sum()),
        "detected_rate": round(float(alarm[y_te == 1].mean()), 6),
        "false_alarm_rate": round(float(alarm[y_te == 0].mean()), 6),
    }


def main() -> None:
    df = cast_canonical_df(pd.read_csv("data/samples/fixture.csv"))
    normal = df[df["label"] == 0].sort_values("timestamp")
    attacks = df[df["label"] == 1]
    cut = int(len(normal) * 0.7)
    normal_train = normal.iloc[:cut]
    normal_test = normal.iloc[cut:]

    results: dict[str, Any] = {
        "method": "IsolationForest trained on normal frames only",
        "calibration": f"threshold = {CALIBRATION_QUANTILE} quantile of normal calibration scores",
        "seeds": SEEDS,
        "by_attack": {},
    }

    for attack in ATTACKS:
        runs = [
            run_fold(normal_train, normal_test, attacks, attack, seed)
            for seed in SEEDS
        ]
        rates = [r["detected_rate"] for r in runs]
        fars = [r["false_alarm_rate"] for r in runs]
        results["by_attack"][attack] = {
            "runs": runs,
            "detected_rate_mean": round(float(np.mean(rates)), 6),
            "detected_rate_min": round(min(rates), 6),
            "detected_rate_max": round(max(rates), 6),
            "false_alarm_rate_mean": round(float(np.mean(fars)), 6),
        }
        print(
            f"{attack}: detected mean={np.mean(rates):.3f} "
            f"range=[{min(rates):.3f}, {max(rates):.3f}] "
            f"false alarm mean={np.mean(fars):.3f}"
        )

    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"report: {OUT}")


if __name__ == "__main__":
    main()