"""Combine standard-split and LOAO run records into the final evaluation report."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from stark.config import REPORTS_DIR

BASELINE_PATH = REPORTS_DIR / "standard_split_baseline.json"
SMOTE_PATH = REPORTS_DIR / "standard_split_smote.json"
LOAO_PATH = REPORTS_DIR / "loao_results.json"
OUTPUT_PATH = REPORTS_DIR / "metrics_final.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required evaluation output is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_report() -> dict[str, Any]:
    baseline = read_json(BASELINE_PATH)
    smote = read_json(SMOTE_PATH)
    loao = read_json(LOAO_PATH)
    baseline_counts = baseline["class_counts_per_split"]
    smote_counts = smote["class_counts_per_split"]
    for split in ("validation", "test"):
        if baseline_counts[split] != smote_counts[split]:
            raise ValueError(
                f"SMOTE changed {split} class counts; refusing to create final report"
            )
        if baseline["split_sizes"][split] != smote["split_sizes"][split]:
            raise ValueError(
                f"SMOTE changed {split} row count; refusing to create final report"
            )

    return {
        "dataset_name": baseline["dataset_name"],
        "generated_at": datetime.now(UTC).isoformat(),
        "split_sizes": baseline["split_sizes"],
        "class_counts_per_split": baseline_counts,
        "model_configuration": {
            "standard_split": baseline["model_configuration"],
            "loao": loao["configurations"]["smote_off"]["model_configuration"],
        },
        "seeds": {
            "standard_split": {
                "smote_off": baseline["seed"],
                "smote_on": smote["seed"],
            },
            "loao": {
                key: config["seeds"] for key, config in loao["configurations"].items()
            },
        },
        "standard_split_runs": {
            "smote_off": baseline,
            "smote_on": smote,
        },
        "loao_per_attack_results": loao["configurations"],
        "latency_percentiles_ms": {
            "smote_off": baseline["latency_percentiles_ms"],
            "smote_on": smote["latency_percentiles_ms"],
        },
        "all_normal_baseline_accuracy": {
            "validation": baseline["validation_metrics"][
                "all_normal_baseline_accuracy"
            ],
            "test": baseline["test_metrics"]["all_normal_baseline_accuracy"],
        },
        "accuracy_reporting_note": "Each standard-split accuracy is paired with its all-normal baseline accuracy and sample/class counts in standard_split_runs.",
    }


def main() -> None:
    report = build_report()
    OUTPUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {OUTPUT_PATH}: standard splits {report['split_sizes']}; "
        f"LOAO modes={list(report['loao_per_attack_results'])}"
    )


if __name__ == "__main__":
    main()
