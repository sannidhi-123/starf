"""Canonical DataFrame schema and validation for STARK v1.0."""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

from stark.utils.exceptions import SchemaValidationError

SCHEMA_VERSION: Final[str] = "1.0"

BYTE_COLUMNS: Final[list[str]] = [f"data_{i}" for i in range(8)]

CANONICAL_COLUMNS: Final[list[str]] = [
    "timestamp",
    "can_id",
    "dlc",
    *BYTE_COLUMNS,
    "is_remote",
    "source",
    "capture",
    "attack_type",
    "label",
    "label_quality",
]

ATTACK_TYPES: Final[tuple[str, ...]] = (
    "normal",
    "dos",
    "fuzzy",
    "gear_spoof",
    "rpm_spoof",
    "impersonation",
    "replay",
    "unknown",
)

LABEL_QUALITIES: Final[tuple[str, ...]] = (
    "frame",
    "window",
    "none",
)

CANONICAL_DTYPES: Final[dict[str, str]] = {
    "timestamp": "float64",
    "can_id": "int64",
    "dlc": "int8",
    "data_0": "int16",
    "data_1": "int16",
    "data_2": "int16",
    "data_3": "int16",
    "data_4": "int16",
    "data_5": "int16",
    "data_6": "int16",
    "data_7": "int16",
    "is_remote": "bool",
    "source": "category",
    "capture": "category",
    "attack_type": "category",
    "label": "int8",
    "label_quality": "category",
}

MAX_CAN_ID: Final[int] = 0x1FFFFFFF


def create_empty_canonical_df() -> pd.DataFrame:
    """Create an empty DataFrame conforming to the STARK canonical schema.

    Returns:
        pd.DataFrame: Empty DataFrame with correct column names, dtypes, and categories.
    """
    return pd.DataFrame(
        {
            "timestamp": pd.Series(dtype=np.float64),
            "can_id": pd.Series(dtype=np.int64),
            "dlc": pd.Series(dtype=np.int8),
            "data_0": pd.Series(dtype=np.int16),
            "data_1": pd.Series(dtype=np.int16),
            "data_2": pd.Series(dtype=np.int16),
            "data_3": pd.Series(dtype=np.int16),
            "data_4": pd.Series(dtype=np.int16),
            "data_5": pd.Series(dtype=np.int16),
            "data_6": pd.Series(dtype=np.int16),
            "data_7": pd.Series(dtype=np.int16),
            "is_remote": pd.Series(dtype=bool),
            "source": pd.Series(dtype="category"),
            "capture": pd.Series(dtype="category"),
            "attack_type": pd.Series(pd.Categorical([], categories=ATTACK_TYPES)),
            "label": pd.Series(dtype=np.int8),
            "label_quality": pd.Series(pd.Categorical([], categories=LABEL_QUALITIES)),
        }
    )


def cast_canonical_df(df: pd.DataFrame) -> pd.DataFrame:
    """Cast an input DataFrame to canonical STARK column dtypes.

    Args:
        df: Input DataFrame containing canonical columns.

    Returns:
        pd.DataFrame: A copy of the DataFrame with canonical dtypes applied.
    """
    res = df.copy()
    res["timestamp"] = res["timestamp"].astype(np.float64)
    res["can_id"] = res["can_id"].astype(np.int64)
    res["dlc"] = res["dlc"].astype(np.int8)
    for col in BYTE_COLUMNS:
        res[col] = res[col].astype(np.int16)
    res["is_remote"] = res["is_remote"].astype(bool)
    res["source"] = res["source"].astype("category")
    res["capture"] = res["capture"].astype("category")
    res["attack_type"] = pd.Categorical(res["attack_type"], categories=ATTACK_TYPES)
    res["label"] = res["label"].astype(np.int8)
    res["label_quality"] = pd.Categorical(
        res["label_quality"], categories=LABEL_QUALITIES
    )
    return res[CANONICAL_COLUMNS]


def validate(df: pd.DataFrame) -> None:
    """Validate that a DataFrame conforms strictly to STARK canonical schema v1.0.

    Args:
        df: The DataFrame to validate.

    Raises:
        SchemaValidationError: If missing columns, wrong dtypes, out-of-range values,
            decreasing timestamps within a capture, or invalid labels are found.
    """
    # 1. Missing columns
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            raise SchemaValidationError(
                f"Missing required column '{col}' at row 0",
                column=col,
                row=0,
            )

    # 2. Column dtypes
    for col, expected_dtype in CANONICAL_DTYPES.items():
        actual_dtype = df[col].dtype.name
        if expected_dtype == "category":
            if not isinstance(df[col].dtype, pd.CategoricalDtype):
                raise SchemaValidationError(
                    f"Column '{col}' at row 0 has invalid dtype '{actual_dtype}', expected 'category'",
                    column=col,
                    row=0,
                )
        else:
            if actual_dtype != expected_dtype:
                raise SchemaValidationError(
                    f"Column '{col}' at row 0 has invalid dtype '{actual_dtype}', expected '{expected_dtype}'",
                    column=col,
                    row=0,
                )

    if len(df) == 0:
        return

    # 3. DLC range: 0 <= dlc <= 8
    bad_dlc = (df["dlc"] < 0) | (df["dlc"] > 8)
    bad_dlc_idx = np.where(bad_dlc)[0]
    if len(bad_dlc_idx) > 0:
        first_bad = int(bad_dlc_idx[0])
        bad_val = df["dlc"].iloc[first_bad]
        raise SchemaValidationError(
            f"Column 'dlc' has value {bad_val} outside allowed range [0, 8] at row {first_bad}",
            column="dlc",
            row=first_bad,
        )

    # 4. CAN ID range: 0 <= can_id <= 0x1FFFFFFF
    bad_can_id = (df["can_id"] < 0) | (df["can_id"] > MAX_CAN_ID)
    bad_can_id_idx = np.where(bad_can_id)[0]
    if len(bad_can_id_idx) > 0:
        first_bad = int(bad_can_id_idx[0])
        bad_val = df["can_id"].iloc[first_bad]
        raise SchemaValidationError(
            f"Column 'can_id' has value {bad_val} outside allowed range [0, 0x1FFFFFFF] at row {first_bad}",
            column="can_id",
            row=first_bad,
        )

    # 5. Payload bytes range: -1 <= data_i <= 255
    for col in BYTE_COLUMNS:
        bad_bytes = (df[col] < -1) | (df[col] > 255)
        bad_byte_idx = np.where(bad_bytes)[0]
        if len(bad_byte_idx) > 0:
            first_bad = int(bad_byte_idx[0])
            bad_val = df[col].iloc[first_bad]
            raise SchemaValidationError(
                f"Column '{col}' has value {bad_val} outside allowed range [-1, 255] at row {first_bad}",
                column=col,
                row=first_bad,
            )

    # 6. Labels: must be in {0, 1}
    bad_labels = ~df["label"].isin([0, 1])
    bad_label_idx = np.where(bad_labels)[0]
    if len(bad_label_idx) > 0:
        first_bad = int(bad_label_idx[0])
        bad_val = df["label"].iloc[first_bad]
        raise SchemaValidationError(
            f"Column 'label' has value {bad_val} outside allowed set {{0, 1}} at row {first_bad}",
            column="label",
            row=first_bad,
        )

    # 7. Attack type: must belong to allowed categories and not be null
    bad_attacks = (
        ~df["attack_type"].astype(str).isin(ATTACK_TYPES) | df["attack_type"].isna()
    )
    bad_attack_idx = np.where(bad_attacks)[0]
    if len(bad_attack_idx) > 0:
        first_bad = int(bad_attack_idx[0])
        bad_val = df["attack_type"].iloc[first_bad]
        raise SchemaValidationError(
            f"Column 'attack_type' has invalid category '{bad_val}' at row {first_bad}",
            column="attack_type",
            row=first_bad,
        )

    # 8. Label quality: must belong to allowed categories and not be null
    bad_qualities = (
        ~df["label_quality"].astype(str).isin(LABEL_QUALITIES)
        | df["label_quality"].isna()
    )
    bad_quality_idx = np.where(bad_qualities)[0]
    if len(bad_quality_idx) > 0:
        first_bad = int(bad_quality_idx[0])
        bad_val = df["label_quality"].iloc[first_bad]
        raise SchemaValidationError(
            f"Column 'label_quality' has invalid category '{bad_val}' at row {first_bad}",
            column="label_quality",
            row=first_bad,
        )

    # 9. Source & capture: must not be null
    for col in ("source", "capture"):
        bad_cat = df[col].isna()
        bad_cat_idx = np.where(bad_cat)[0]
        if len(bad_cat_idx) > 0:
            first_bad = int(bad_cat_idx[0])
            raise SchemaValidationError(
                f"Column '{col}' contains null/missing category value at row {first_bad}",
                column=col,
                row=first_bad,
            )

    # 10. Timestamp: finite and non-decreasing within each capture
    ts_arr = df["timestamp"].to_numpy()
    bad_ts = np.isnan(ts_arr) | np.isinf(ts_arr)
    bad_ts_idx = np.where(bad_ts)[0]
    if len(bad_ts_idx) > 0:
        first_bad = int(bad_ts_idx[0])
        raise SchemaValidationError(
            f"Column 'timestamp' contains non-finite value at row {first_bad}",
            column="timestamp",
            row=first_bad,
        )

    first_ts_bad_row: int | None = None
    first_ts_bad_cap: str | None = None
    first_ts_bad_vals: tuple[float, float] | None = None

    unique_captures = (
        df["capture"].cat.categories
        if hasattr(df["capture"], "cat")
        else df["capture"].unique()
    )
    for cap in unique_captures:
        mask = (df["capture"] == cap).to_numpy()
        cap_indices = np.where(mask)[0]
        if len(cap_indices) > 1:
            ts = df["timestamp"].iloc[cap_indices].to_numpy()
            diffs = np.diff(ts)
            decreasing = np.where(diffs < 0.0)[0]
            if len(decreasing) > 0:
                first_bad_rel = decreasing[0] + 1
                bad_row = int(cap_indices[first_bad_rel])
                if first_ts_bad_row is None or bad_row < first_ts_bad_row:
                    first_ts_bad_row = bad_row
                    first_ts_bad_cap = str(cap)
                    first_ts_bad_vals = (ts[decreasing[0]], ts[first_bad_rel])

    if first_ts_bad_row is not None and first_ts_bad_vals is not None:
        raise SchemaValidationError(
            f"Column 'timestamp' decreases at row {first_ts_bad_row} within capture '{first_ts_bad_cap}' "
            f"({first_ts_bad_vals[1]} < {first_ts_bad_vals[0]})",
            column="timestamp",
            row=first_ts_bad_row,
        )
