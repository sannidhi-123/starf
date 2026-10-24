"""Feature matrix builder converting canonical DataFrames to model arrays."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stark.features.registry import FEATURE_NAMES
from stark.features.state import FeatureBaseline, FeatureState
from stark.utils.logging import get_logger

logger = get_logger(__name__)


def build_feature_dataframe(
    df: pd.DataFrame,
    baseline: FeatureBaseline | None = None,
) -> tuple[pd.DataFrame, FeatureBaseline]:
    """Extract causal 20 model features from a canonical DataFrame.

    Args:
        df: Canonical input DataFrame.
        baseline: Precomputed training baseline. If None, fits on df normal frames.

    Returns:
        tuple[pd.DataFrame, FeatureBaseline]:
            DataFrame containing the 20 model feature columns and the baseline.
    """
    if baseline is None:
        baseline = FeatureBaseline.fit(df)

    state = FeatureState(baseline=baseline)
    records: list[dict[str, float]] = []

    # Iteration preserves causality row-by-row
    for _, row in df.iterrows():
        feat_dict = state.update(row)
        records.append(feat_dict)

    feat_df = pd.DataFrame(records, columns=FEATURE_NAMES).astype(np.float32)
    return feat_df, baseline


def build_feature_matrix(
    df: pd.DataFrame,
    baseline: FeatureBaseline | None = None,
) -> tuple[np.ndarray, np.ndarray, FeatureBaseline]:
    """Convert canonical DataFrame into float32 feature matrix and label vector.

    Args:
        df: Canonical input DataFrame.
        baseline: Precomputed training baseline. If None, fits on df normal frames.

    Returns:
        tuple[np.ndarray, np.ndarray, FeatureBaseline]:
            X (float32 array of shape (N, 20)),
            y (uint8 array of shape (N,)),
            baseline (FeatureBaseline)

    Raises:
        ValueError: If resulting matrix contains NaN or Inf values.
    """
    if df.empty:
        X_empty = np.empty((0, len(FEATURE_NAMES)), dtype=np.float32)
        y_empty = np.empty((0,), dtype=np.uint8)
        return X_empty, y_empty, baseline if baseline is not None else FeatureBaseline()

    feat_df, fitted_baseline = build_feature_dataframe(df, baseline=baseline)
    X = feat_df.to_numpy(dtype=np.float32, copy=False)
    y = df["label"].to_numpy(dtype=np.uint8, copy=False)

    # Verification: strictly no NaN or Inf
    if np.isnan(X).any() or np.isinf(X).any():
        bad_rows = np.where(np.isnan(X).any(axis=1) | np.isinf(X).any(axis=1))[0]
        raise ValueError(
            f"Feature matrix contains non-finite values (NaN or Inf) at row indices: {bad_rows[:10]}"
        )

    logger.info("Built feature matrix X=%s, y=%s", X.shape, y.shape)
    return X, y, fitted_baseline
