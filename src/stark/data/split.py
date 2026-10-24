"""Time-ordered dataset splitting for STARK.

Enforces Rule 4: Splits are strictly time-ordered per capture (70/15/15), never shuffled.
"""

from __future__ import annotations

import pandas as pd

from stark.schema import cast_canonical_df, validate
from stark.utils.logging import get_logger

logger = get_logger(__name__)


def split_time_ordered(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split canonical DataFrame chronologically per capture into train, val, and test splits.

    Strictly preserves temporal ordering within each capture run without shuffling.

    Args:
        df: Canonical input DataFrame.
        train_ratio: Fraction of each capture allocated to training (default 0.70).
        val_ratio: Fraction of each capture allocated to validation (default 0.15).
        test_ratio: Fraction of each capture allocated to testing (default 0.15).

    Returns:
        tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
            (train_df, val_df, test_df) each conforming to the STARK canonical schema.

    Raises:
        ValueError: If ratios do not sum to 1.0 or if a capture is too small to split.
    """
    if abs((train_ratio + val_ratio + test_ratio) - 1.0) > 1e-6:
        raise ValueError(
            f"Split ratios must sum to 1.0, got {train_ratio} + {val_ratio} + {test_ratio} = "
            f"{train_ratio + val_ratio + test_ratio}"
        )

    if df.empty:
        raise ValueError("Cannot split empty DataFrame.")

    train_chunks: list[pd.DataFrame] = []
    val_chunks: list[pd.DataFrame] = []
    test_chunks: list[pd.DataFrame] = []

    unique_captures = (
        df["capture"].cat.categories
        if hasattr(df["capture"], "cat")
        else df["capture"].unique()
    )

    for cap in unique_captures:
        cap_df = df[df["capture"] == cap]
        if cap_df.empty:
            continue

        n_rows = len(cap_df)
        if n_rows < 3:
            raise ValueError(
                f"Capture '{cap}' has only {n_rows} rows, too few to split 70/15/15."
            )

        train_end = int(n_rows * train_ratio)
        val_end = int(n_rows * (train_ratio + val_ratio))

        # Ensure at least 1 row in train if possible
        train_end = max(train_end, 1)
        val_end = max(val_end, train_end + 1)
        val_end = min(val_end, n_rows - 1 if n_rows >= 3 else n_rows)

        train_chunks.append(cap_df.iloc[:train_end])
        val_chunks.append(cap_df.iloc[train_end:val_end])
        test_chunks.append(cap_df.iloc[val_end:])

    train_df = cast_canonical_df(pd.concat(train_chunks, ignore_index=True))
    val_df = cast_canonical_df(pd.concat(val_chunks, ignore_index=True))
    test_df = cast_canonical_df(pd.concat(test_chunks, ignore_index=True))

    validate(train_df)
    validate(val_df)
    validate(test_df)

    logger.info(
        "Time-ordered split complete: %d train rows, %d val rows, %d test rows",
        len(train_df),
        len(val_df),
        len(test_df),
    )
    return train_df, val_df, test_df
