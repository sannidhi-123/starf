"""Tests for STARK data cleaning and merging pipeline."""

from __future__ import annotations

import pandas as pd
import pytest

from stark.data.clean import clean_canonical_df
from stark.data.merge import merge_captures, validate_no_cross_source_merge
from stark.schema import cast_canonical_df, validate


def _make_sample_row(
    timestamp: float = 1478198376.5,
    can_id: int | str = 0x120,
    dlc: int = 8,
    data: list[int] | None = None,
    capture: str = "cap_1",
    source: str = "car_hacking",
    attack_type: str = "normal",
    label: int = 0,
    is_remote: bool = False,
) -> dict:
    if data is None:
        data = [0] * 8
    padded = list(data) + [-1] * (8 - len(data))
    return {
        "timestamp": timestamp,
        "can_id": can_id,
        "dlc": dlc,
        **{f"data_{i}": padded[i] for i in range(8)},
        "is_remote": is_remote,
        "source": source,
        "capture": capture,
        "attack_type": attack_type,
        "label": label,
        "label_quality": "frame",
    }


def test_clean_ragged_dlc3_pads_to_minus_one():
    """Verify clean_canonical_df forces missing bytes (DLC < 8) to -1."""
    # Introduce row with DLC=3 and erroneous zeros in data_3..data_7
    raw_row = _make_sample_row(dlc=3, data=[10, 20, 30, 0, 0, 0, 0, 0])
    df = pd.DataFrame([raw_row])

    cleaned, report = clean_canonical_df(df)
    assert len(cleaned) == 1
    assert report.rows_out == 1
    row = cleaned.iloc[0]
    assert row["data_0"] == 10
    assert row["data_1"] == 20
    assert row["data_2"] == 30
    for k in range(3, 8):
        assert row[f"data_{k}"] == -1
    validate(cleaned)


def test_clean_hex_id_conversion():
    """Verify clean_canonical_df converts string hex '0316' to integer 790."""
    raw_row = _make_sample_row(can_id="0316")
    df = pd.DataFrame([raw_row])

    cleaned, report = clean_canonical_df(df)
    assert len(cleaned) == 1
    assert report.rows_out == 1
    assert cleaned.iloc[0]["can_id"] == 790
    assert cleaned["can_id"].dtype == "int64"
    validate(cleaned)


def test_clean_rebase_timestamps_to_zero():
    """Verify timestamps are re-based so each capture starts at 0.0."""
    rows = [
        _make_sample_row(timestamp=1478198376.5, capture="cap_A"),
        _make_sample_row(timestamp=1478198376.6, capture="cap_A"),
        _make_sample_row(timestamp=1478198376.8, capture="cap_A"),
        _make_sample_row(timestamp=1500000000.1, capture="cap_B"),
        _make_sample_row(timestamp=1500000000.3, capture="cap_B"),
    ]
    df = pd.DataFrame(rows)

    cleaned, _ = clean_canonical_df(df)

    cap_a = cleaned[cleaned["capture"] == "cap_A"]
    assert cap_a["timestamp"].iloc[0] == 0.0
    assert pytest.approx(cap_a["timestamp"].iloc[1]) == 0.1
    assert pytest.approx(cap_a["timestamp"].iloc[2]) == 0.3

    cap_b = cleaned[cleaned["capture"] == "cap_B"]
    assert cap_b["timestamp"].iloc[0] == 0.0
    assert pytest.approx(cap_b["timestamp"].iloc[1]) == 0.2
    validate(cleaned)


def test_periodic_duplicates_kept():
    """Verify legitimate periodic duplicates (up to 2 occurrences) are kept."""
    # Exactly 2 identical frames
    row = _make_sample_row(timestamp=100.0, can_id=0x120)
    df = pd.DataFrame([row, row])

    cleaned, report = clean_canonical_df(df)
    assert len(cleaned) == 2
    assert report.dropped_per_reason["excess_duplicates"] == 0
    validate(cleaned)


def test_parse_artifact_duplicates_dropped_and_counted():
    """Verify duplicate frames appearing > 2 times have excess occurrences dropped and counted."""
    row = _make_sample_row(timestamp=100.0, can_id=0x120)
    # 4 identical frames: exactly 2 kept, 2 dropped
    df = pd.DataFrame([row, row, row, row])

    cleaned, report = clean_canonical_df(df)
    assert len(cleaned) == 2
    assert report.rows_in == 4
    assert report.rows_out == 2
    assert report.dropped_per_reason["excess_duplicates"] == 2
    validate(cleaned)


def test_row_count_within_1_percent():
    """Verify cleaned row count is within 1% of raw valid input."""
    rows = [_make_sample_row(timestamp=100.0 + i * 0.001) for i in range(1000)]
    df = pd.DataFrame(rows)

    cleaned, report = clean_canonical_df(df)
    assert len(cleaned) == 1000
    assert report.rows_out == 1000
    assert abs(len(cleaned) - 1000) / 1000 <= 0.01


def test_merge_rejects_cross_source():
    """Verify merge_captures raises ValueError when merging Car-Hacking and OTIDS."""
    df_car = cast_canonical_df(pd.DataFrame([_make_sample_row(source="car_hacking")]))
    df_otids = cast_canonical_df(pd.DataFrame([_make_sample_row(source="otids")]))

    with pytest.raises(
        ValueError, match="Cannot merge datasets from different sources"
    ):
        merge_captures([df_car, df_otids])

    with pytest.raises(
        ValueError, match="Cannot merge datasets from different sources"
    ):
        validate_no_cross_source_merge([df_car, df_otids])


def test_merge_same_source_succeeds():
    """Verify merge_captures succeeds for captures of the same source."""
    df1 = cast_canonical_df(
        pd.DataFrame([_make_sample_row(capture="run_1", source="car_hacking")])
    )
    df2 = cast_canonical_df(
        pd.DataFrame([_make_sample_row(capture="run_2", source="car_hacking")])
    )

    merged = merge_captures([df1, df2])
    assert len(merged) == 2
    assert merged["source"].iloc[0] == "car_hacking"
    validate(merged)
