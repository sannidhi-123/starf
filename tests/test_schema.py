"""Tests for STARK canonical schema definition and validation."""

from __future__ import annotations

import pandas as pd
import pytest

from stark.config import SAMPLES_DIR
from stark.schema import (
    ATTACK_TYPES,
    CANONICAL_COLUMNS,
    LABEL_QUALITIES,
    SCHEMA_VERSION,
    SchemaValidationError,
    cast_canonical_df,
    create_empty_canonical_df,
    validate,
)


def _make_valid_df(n_rows: int = 5) -> pd.DataFrame:
    """Create a minimal valid canonical DataFrame for testing."""
    records = []
    for i in range(n_rows):
        records.append(
            {
                "timestamp": float(i) * 0.1,
                "can_id": int(0x120 + i),
                "dlc": 8,
                "data_0": 0,
                "data_1": 1,
                "data_2": 2,
                "data_3": 3,
                "data_4": 4,
                "data_5": 5,
                "data_6": 6,
                "data_7": 7,
                "is_remote": False,
                "source": "car_hacking",
                "capture": "capture_1",
                "attack_type": "normal",
                "label": 0,
                "label_quality": "frame",
            }
        )
    df = pd.DataFrame(records)
    return cast_canonical_df(df)


def test_schema_version_and_columns():
    """Verify schema version is 1.0 and canonical column set matches design."""
    assert SCHEMA_VERSION == "1.0"
    assert len(CANONICAL_COLUMNS) == 17
    assert CANONICAL_COLUMNS[0] == "timestamp"
    assert CANONICAL_COLUMNS[1] == "can_id"
    assert CANONICAL_COLUMNS[2] == "dlc"
    assert CANONICAL_COLUMNS[3:11] == [f"data_{i}" for i in range(8)]
    assert "dos" in ATTACK_TYPES
    assert "fuzzy" in ATTACK_TYPES
    assert "frame" in LABEL_QUALITIES


def test_valid_frame_passes():
    """A valid canonical dataframe must pass validation without error."""
    df = _make_valid_df(10)
    validate(df)


def test_empty_dataframe_passes():
    """An empty DataFrame with correct canonical columns and dtypes passes validation."""
    df = create_empty_canonical_df()
    validate(df)


def test_missing_column_raises():
    """Missing a required column must raise SchemaValidationError naming the column."""
    df = _make_valid_df()
    df_missing = df.drop(columns=["is_remote"])

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(df_missing)

    assert exc_info.value.column == "is_remote"
    assert exc_info.value.row == 0
    assert "is_remote" in str(exc_info.value)


def test_wrong_dtype_raises():
    """Incorrect column dtype must raise SchemaValidationError naming column and row."""
    df = _make_valid_df()
    # Change can_id from int64 to int32
    df["can_id"] = df["can_id"].astype("int32")

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(df)

    assert exc_info.value.column == "can_id"
    assert exc_info.value.row == 0
    assert "can_id" in str(exc_info.value)


def test_dlc_out_of_range_raises():
    """DLC = 9 or negative must raise SchemaValidationError naming 'dlc' and bad row."""
    df = _make_valid_df(5)
    bad_row = 2
    df.loc[bad_row, "dlc"] = 9

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(df)

    assert exc_info.value.column == "dlc"
    assert exc_info.value.row == bad_row
    assert "dlc" in str(exc_info.value)

    # Test negative DLC
    df.loc[bad_row, "dlc"] = -1
    with pytest.raises(SchemaValidationError) as exc_info:
        validate(df)
    assert exc_info.value.column == "dlc"
    assert exc_info.value.row == bad_row


def test_out_of_range_can_id_raises():
    """CAN ID outside 0..0x1FFFFFFF must raise SchemaValidationError naming 'can_id'."""
    df = _make_valid_df(5)
    bad_row = 3
    # 0x20000000 exceeds 29-bit max (0x1FFFFFFF = 536870911)
    df.loc[bad_row, "can_id"] = 0x20000000

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(df)

    assert exc_info.value.column == "can_id"
    assert exc_info.value.row == bad_row
    assert "can_id" in str(exc_info.value)

    # Negative CAN ID
    df.loc[bad_row, "can_id"] = -5
    with pytest.raises(SchemaValidationError) as exc_info:
        validate(df)
    assert exc_info.value.column == "can_id"
    assert exc_info.value.row == bad_row


def test_byte_outside_range_raises():
    """Byte outside -1..255 must raise SchemaValidationError naming the byte column and row."""
    df = _make_valid_df(5)
    bad_row = 4
    df.loc[bad_row, "data_3"] = 256

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(df)

    assert exc_info.value.column == "data_3"
    assert exc_info.value.row == bad_row
    assert "data_3" in str(exc_info.value)

    df.loc[bad_row, "data_3"] = -2
    with pytest.raises(SchemaValidationError) as exc_info:
        validate(df)
    assert exc_info.value.column == "data_3"
    assert exc_info.value.row == bad_row


def test_decreasing_timestamp_raises():
    """Decreasing timestamps within a single capture must raise SchemaValidationError."""
    df = _make_valid_df(4)
    # Timestamps originally: 0.0, 0.1, 0.2, 0.3
    # Introduce backward step at row 2: 0.2 -> 0.05
    df.loc[2, "timestamp"] = 0.05

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(df)

    assert exc_info.value.column == "timestamp"
    assert exc_info.value.row == 2
    assert "timestamp" in str(exc_info.value)


def test_labels_outside_zero_one_raises():
    """Label outside {0, 1} must raise SchemaValidationError naming 'label' and row."""
    df = _make_valid_df(5)
    bad_row = 1
    df.loc[bad_row, "label"] = 2

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(df)

    assert exc_info.value.column == "label"
    assert exc_info.value.row == bad_row
    assert "label" in str(exc_info.value)


def test_invalid_attack_type_raises():
    """Invalid category in attack_type must raise SchemaValidationError."""
    df = _make_valid_df(5)
    # Add an unlisted category
    df["attack_type"] = df["attack_type"].astype(str)
    df.loc[2, "attack_type"] = "ransomware"
    df["attack_type"] = df["attack_type"].astype("category")

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(df)

    assert exc_info.value.column == "attack_type"
    assert exc_info.value.row == 2
    assert "attack_type" in str(exc_info.value)


def test_fixture_csv_loads_and_passes_validation():
    """Verify data/samples/fixture.csv exists, loads, conforms to schema and counts."""
    fixture_path = SAMPLES_DIR / "fixture.csv"
    assert fixture_path.exists(), f"Fixture file missing: {fixture_path}"

    raw_df = pd.read_csv(fixture_path)
    df = cast_canonical_df(raw_df)

    # 1. Passes validation without raising SchemaValidationError
    validate(df)

    # 2. Approximately 5,000 canonical rows
    assert len(df) == 5000

    # 3. Timestamp starts at 0.0 and is monotonic non-decreasing
    assert df["timestamp"].iloc[0] == 0.0
    diffs = df["timestamp"].diff().dropna()
    assert (diffs >= 0.0).all()

    # 4. Source labeled as synthetic
    assert (df["source"] == "synthetic").all()

    # 5. Normal traffic plus >= 200 frames of dos, fuzzy, gear_spoof, rpm_spoof
    counts = df["attack_type"].value_counts()
    assert counts["normal"] >= 1000
    assert counts["dos"] >= 200
    assert counts["fuzzy"] >= 200
    assert counts["gear_spoof"] >= 200
    assert counts["rpm_spoof"] >= 200

    # 6. Missing bytes (DLC < 8) are stored as -1, never 0
    sub_8 = df[df["dlc"] < 8]
    assert len(sub_8) > 0, "Fixture should have frames with DLC < 8"
    for _, row in sub_8.iterrows():
        dlc_val = int(row["dlc"])
        for byte_idx in range(dlc_val, 8):
            assert row[f"data_{byte_idx}"] == -1
