"""Cleaning and sanitization pipeline for STARK canonical CAN DataFrames."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from stark.schema import (
    BYTE_COLUMNS,
    MAX_CAN_ID,
    cast_canonical_df,
    create_empty_canonical_df,
    validate,
)
from stark.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CleaningReport:
    """Report summarizing input, output, and dropped frame counts by reason.

    Attributes:
        rows_in: Total count of input rows before cleaning.
        rows_out: Final count of valid canonical rows after cleaning.
        dropped_per_reason: Breakdown of dropped rows by specific cause.
    """

    rows_in: int = 0
    rows_out: int = 0
    dropped_per_reason: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary representation."""
        return {
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "dropped_per_reason": dict(self.dropped_per_reason),
        }


def clean_canonical_df(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, CleaningReport]:
    """Clean, sanitize, and validate a canonical CAN DataFrame.

    This function enforces:
    1. Hex to integer conversion for ID and payload columns.
    2. Missing byte padding to -1 for DLC < 8 (Rule 1).
    3. Monotonic sorting and timestamp re-basing so each capture starts at 0.0 (Rule 2).
    4. Duplicate policy: Preserves legitimate periodic duplicates (up to 2 occurrences);
       drops lines that are byte-identical with identical full-precision timestamps appearing
       more than twice (Rule 3).
    5. Schema validation according to SCHEMA_VERSION 1.0.

    Args:
        df: Raw parsed or semi-cleaned DataFrame.

    Returns:
        tuple[pd.DataFrame, CleaningReport]: Cleaned canonical DataFrame and audit report.
    """
    rows_in = len(df)
    dropped_per_reason: dict[str, int] = {
        "unparseable": 0,
        "dlc_out_of_range": 0,
        "out_of_range_can_id": 0,
        "corrupted_byte": 0,
        "excess_duplicates": 0,
    }

    if df.empty:
        empty_clean = create_empty_canonical_df()
        return empty_clean, CleaningReport(
            rows_in=0, rows_out=0, dropped_per_reason=dropped_per_reason
        )

    res = df.copy()

    # 1. Type conversions: Ensure can_id is integer (hex strings converted to decimal)
    if res["can_id"].dtype == object:

        def _parse_id(val: Any) -> int:
            if isinstance(val, str):
                return int(val.strip(), 16)
            return int(val)

        res["can_id"] = res["can_id"].apply(_parse_id)

    # Convert DLC to integer
    res["dlc"] = res["dlc"].astype(int)

    # 2. Filter out-of-range DLC [0, 8]
    valid_dlc = (res["dlc"] >= 0) & (res["dlc"] <= 8)
    dropped_dlc = int((~valid_dlc).sum())
    if dropped_dlc > 0:
        logger.warning("Dropping %d rows with DLC outside [0, 8]", dropped_dlc)
        dropped_per_reason["dlc_out_of_range"] += dropped_dlc
        res = res[valid_dlc].reset_index(drop=True)

    # 3. Filter out-of-range CAN ID [0, 0x1FFFFFFF]
    valid_id = (res["can_id"] >= 0) & (res["can_id"] <= MAX_CAN_ID)
    dropped_id = int((~valid_id).sum())
    if dropped_id > 0:
        logger.warning(
            "Dropping %d rows with CAN ID outside [0, 0x1FFFFFFF]", dropped_id
        )
        dropped_per_reason["out_of_range_can_id"] += dropped_id
        res = res[valid_id].reset_index(drop=True)

    # 4. Enforce Rule 1: Missing bytes (DLC < 8) are stored as -1, never 0.
    for byte_idx in range(8):
        col = f"data_{byte_idx}"
        if col not in res.columns:
            res[col] = -1
        # If payload byte is missing (dlc <= byte_idx), strictly set to -1
        res.loc[res["dlc"] <= byte_idx, col] = -1
        res[col] = res[col].fillna(-1).astype(int)

    # 5. Sort chronologically by capture and timestamp
    res["timestamp"] = res["timestamp"].astype(float)
    res = res.sort_values(["capture", "timestamp"], kind="mergesort", ignore_index=True)

    # 6. Enforce Rule 3: Do not drop duplicate frames in general. Drop only lines that are
    # byte-identical, have identical full-precision timestamps, and appear more than twice.
    dup_cols = ["capture", "timestamp", "can_id", "dlc", *BYTE_COLUMNS, "is_remote"]
    cum_counts = res.groupby(dup_cols, observed=True).cumcount()
    excess_mask = cum_counts >= 2
    excess_count = int(excess_mask.sum())
    if excess_count > 0:
        logger.info(
            "Dropping %d excess duplicate frames (occurrence > 2 with identical timestamp and payload)",
            excess_count,
        )
        dropped_per_reason["excess_duplicates"] += excess_count
        res = res[~excess_mask].reset_index(drop=True)

    # 7. Enforce Rule 2: Re-base timestamps so each capture starts at 0.0
    for cap in res["capture"].unique():
        cap_mask = res["capture"] == cap
        t_start = res.loc[cap_mask, "timestamp"].iloc[0]
        res.loc[cap_mask, "timestamp"] = (
            res.loc[cap_mask, "timestamp"] - t_start
        ).round(6)

    # Cast to canonical types and validate
    clean_df = cast_canonical_df(res)
    validate(clean_df)

    rows_out = len(clean_df)
    report = CleaningReport(
        rows_in=rows_in,
        rows_out=rows_out,
        dropped_per_reason=dropped_per_reason,
    )
    logger.info(
        "Cleaned dataset: %d rows in, %d rows out, %d dropped",
        rows_in,
        rows_out,
        rows_in - rows_out,
    )
    return clean_df, report
