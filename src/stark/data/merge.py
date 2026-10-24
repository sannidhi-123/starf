"""Dataset merging policies and cross-source isolation for STARK."""

from __future__ import annotations

import pandas as pd

from stark.schema import cast_canonical_df, validate
from stark.utils.logging import get_logger

logger = get_logger(__name__)


def validate_no_cross_source_merge(dfs: list[pd.DataFrame]) -> None:
    """Ensure datasets from different sources (e.g. Car-Hacking and OTIDS) are not merged.

    Args:
        dfs: List of DataFrames to verify.

    Raises:
        ValueError: If multiple different sources are detected across DataFrames.
    """
    sources: set[str] = set()
    for df in dfs:
        if "source" in df.columns and not df.empty:
            sources.update(df["source"].dropna().unique().astype(str))

    if len(sources) > 1:
        raise ValueError(
            f"Cannot merge datasets from different sources for training: "
            f"found sources {sorted(sources)}. "
            f"Car-Hacking and OTIDS originate from different vehicular architectures and must remain separate."
        )


def merge_captures(dfs: list[pd.DataFrame]) -> pd.DataFrame:
    """Merge multiple capture DataFrames belonging to the same source.

    Args:
        dfs: List of canonical DataFrames to merge.

    Returns:
        pd.DataFrame: Merged canonical DataFrame.

    Raises:
        ValueError: If empty list is provided or if cross-source datasets are provided.
    """
    if not dfs:
        raise ValueError("Cannot merge empty list of DataFrames.")

    validate_no_cross_source_merge(dfs)

    merged = pd.concat(dfs, ignore_index=True)
    canonical_merged = cast_canonical_df(merged)
    validate(canonical_merged)
    logger.info(
        "Successfully merged %d captures from source '%s' (total %d rows)",
        len(dfs),
        canonical_merged["source"].iloc[0] if len(canonical_merged) > 0 else "unknown",
        len(canonical_merged),
    )
    return canonical_merged
