"""CLI script to build and save feature matrices from canonical CAN datasets."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from stark.config import PROCESSED_DATA_DIR, SAMPLES_DIR
from stark.data.split import split_time_ordered
from stark.features.build import build_feature_matrix
from stark.features.state import FeatureBaseline
from stark.utils.logging import get_logger

logger = get_logger("02_build_features")


def main() -> None:
    """Build feature matrices and write them to disk."""
    parser = argparse.ArgumentParser(
        description="Extract causal 20 model features and build training/eval matrices."
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Path to input canonical Parquet or CSV file (defaults to data/samples/fixture.csv)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Destination directory for feature matrices (defaults to data/processed/features/)",
    )
    parser.add_argument(
        "--split",
        action="store_true",
        help="Perform time-ordered 70/15/15 split and export train/val/test matrices",
    )
    args = parser.parse_args()

    if args.input:
        in_path = Path(args.input)
    else:
        in_path = SAMPLES_DIR / "fixture.csv"

    if not in_path.exists():
        raise FileNotFoundError(f"Input dataset not found: {in_path}")

    out_dir = (
        Path(args.output_dir) if args.output_dir else (PROCESSED_DATA_DIR / "features")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading input dataset from %s", in_path)
    if in_path.suffix == ".parquet":
        df = pd.read_parquet(in_path)
    else:
        from stark.schema import cast_canonical_df

        df = cast_canonical_df(pd.read_csv(in_path))

    if args.split:
        logger.info("Splitting dataset chronologically 70/15/15 per capture")
        train_df, val_df, test_df = split_time_ordered(df)

        # Fit baseline strictly on training normal frames
        logger.info("Fitting baseline on training normal frames")
        baseline = FeatureBaseline.fit(train_df)

        logger.info("Transforming train split")
        X_train, y_train, _ = build_feature_matrix(train_df, baseline=baseline)

        logger.info("Transforming val split")
        X_val, y_val, _ = build_feature_matrix(val_df, baseline=baseline)

        logger.info("Transforming test split")
        X_test, y_test, _ = build_feature_matrix(test_df, baseline=baseline)

        np.save(out_dir / "X_train.npy", X_train)
        np.save(out_dir / "y_train.npy", y_train)
        np.save(out_dir / "X_val.npy", X_val)
        np.save(out_dir / "y_val.npy", y_val)
        np.save(out_dir / "X_test.npy", X_test)
        np.save(out_dir / "y_test.npy", y_test)
        joblib.dump(baseline, out_dir / "baseline.joblib")

        print(
            f"Successfully built split feature matrices in {out_dir}:\n"
            f"  X_train: {X_train.shape}, y_train: {y_train.shape}\n"
            f"  X_val:   {X_val.shape}, y_val:   {y_val.shape}\n"
            f"  X_test:  {X_test.shape}, y_test:  {y_test.shape}"
        )
    else:
        X, y, baseline = build_feature_matrix(df)
        np.save(out_dir / "X.npy", X)
        np.save(out_dir / "y.npy", y)
        joblib.dump(baseline, out_dir / "baseline.joblib")
        print(
            f"Successfully built feature matrix in {out_dir}: X={X.shape}, y={y.shape}"
        )


if __name__ == "__main__":
    main()
