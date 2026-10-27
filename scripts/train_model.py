"""Train a reproducible optional Random Forest or XGBoost model from CAN CSV.

Example: python scripts/train_model.py --data data/samples/training.csv
External benchmark datasets are not included in this repository; do not use
demo fixtures to report benchmark performance.
"""

# ruff: noqa: E402  – sys.path adjustment before project imports is intentional

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stark.ml.features import (
    FEATURE_NAMES,
    frame_to_vector,
    normalize_dataset,
)
from stark.pipeline.features import StreamingFeatures


def prepare_xy(path: Path) -> tuple[List[List[float]], List[str]]:
    raw = pd.read_csv(path, dtype=str)
    data = normalize_dataset(raw)
    if "label" not in data:
        raise ValueError("Training CSV needs a label/flag/class/attack_type column")
    extractor = StreamingFeatures()
    features: List[List[float]] = []
    labels: List[str] = []
    for _, row in data.iterrows():
        record: Dict[str, Any] = row.to_dict()
        # Standardize payload to the streamer's byte representation.
        if "payload" not in record:
            record["payload"] = "".join(
                str(record.get(f"DATA[{i}]", "")).strip().zfill(2)
                for i in range(8)
                if str(record.get(f"DATA[{i}]", "")).strip()
            )
        features.append(frame_to_vector(extractor.update(record)))
        labels.append(str(row["label"]))
    if len(set(labels)) < 2:
        raise ValueError("Training requires at least two distinct labels")
    return features, labels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument(
        "--model", choices=("random_forest", "xgboost"), default="random_forest"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "models" / "starf_model.pkl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not args.data.is_file():
        parser.error(f"Dataset not found: {args.data}")

    x, y = prepare_xy(args.data)
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import LabelEncoder
        from sklearn.metrics import classification_report
        from sklearn.model_selection import train_test_split
    except ImportError as exc:
        raise SystemExit("Install backend/requirements-ml.txt to train models") from exc

    label_encoder = LabelEncoder().fit(y)
    y_encoded = label_encoder.transform(y)
    if args.model == "random_forest":
        estimator = RandomForestClassifier(
            n_estimators=250,
            class_weight="balanced",
            random_state=args.seed,
            n_jobs=-1,
            min_samples_leaf=2,
        )
    else:
        try:
            from xgboost import XGBClassifier
        except ImportError as exc:
            raise SystemExit(
                "XGBoost requested; install backend/requirements-ml.txt"
            ) from exc
        estimator = XGBClassifier(
            n_estimators=250,
            max_depth=6,
            learning_rate=0.08,
            objective="multi:softprob",
            eval_metric="mlogloss",
            random_state=args.seed,
        )
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y_encoded,
        test_size=0.2,
        random_state=args.seed,
        stratify=y_encoded,
    )
    estimator.fit(x_train, y_train)
    report = classification_report(
        y_test, estimator.predict(x_test), output_dict=True, zero_division=0
    )
    artifact = {
        "model": estimator,
        "label_encoder": label_encoder,
        "model_type": args.model,
        "feature_names": list(FEATURE_NAMES),
        "classes": [str(c) for c in label_encoder.classes_],
        "seed": args.seed,
        "train_rows": len(y_train),
        "test_rows": len(y_test),
        "evaluation": report,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("wb") as stream:
        pickle.dump(artifact, stream)
    metrics_path = args.out.with_suffix(".metrics.json")
    metrics_path.write_text(
        json.dumps({k: v for k, v in artifact.items() if k != "model"}, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "artifact": str(args.out),
                "metrics": str(metrics_path),
                "test_rows": len(y_test),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
