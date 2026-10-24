"""Tests for STARK feature engineering, causal state, and matrix building."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stark.config import SAMPLES_DIR
from stark.data.split import split_time_ordered
from stark.features.build import build_feature_dataframe, build_feature_matrix
from stark.features.registry import FEATURE_NAMES, get_feature_count, get_feature_names
from stark.features.state import FeatureBaseline
from stark.schema import cast_canonical_df


def _make_frame(
    t: float,
    cid: int,
    dlc: int = 8,
    data: list[int] | None = None,
    capture: str = "cap_1",
    label: int = 0,
) -> dict:
    if data is None:
        data = [0] * dlc
    padded = list(data) + [-1] * (8 - dlc)
    return {
        "timestamp": float(t),
        "can_id": int(cid),
        "dlc": int(dlc),
        **{f"data_{i}": padded[i] for i in range(8)},
        "is_remote": False,
        "source": "synthetic",
        "capture": capture,
        "attack_type": "normal" if label == 0 else "dos",
        "label": label,
        "label_quality": "frame",
    }


def test_registry_feature_count_is_twenty():
    """Verify registry single source of truth specifies exactly 20 model features."""
    assert len(FEATURE_NAMES) == 20
    assert get_feature_count() == 20
    assert get_feature_names() == FEATURE_NAMES
    # Confirm rule-derived features are NOT present in Member 1 registry
    assert "rule_id_whitelist" not in FEATURE_NAMES
    assert "rule_dlc_violation" not in FEATURE_NAMES


def test_feature_causality():
    """Verify causality: rows[:n] features are identical whether computed on rows[:n] or rows[:n+500]."""
    # Create 600 frames
    records = []
    for i in range(600):
        records.append(_make_frame(t=i * 0.001, cid=0x100 + (i % 5)))
    full_df = cast_canonical_df(pd.DataFrame(records))

    baseline = FeatureBaseline.fit(full_df.iloc[:200])

    X_full, _, _ = build_feature_matrix(full_df, baseline=baseline)
    X_prefix, _, _ = build_feature_matrix(full_df.iloc[:100], baseline=baseline)

    # First 100 rows must be numerically identical
    assert np.allclose(
        X_full[:100], X_prefix, atol=1e-6
    ), "Causality violated: future rows changed past features!"


def test_dt_same_id_matches_synthetic_periodic_stream():
    """Verify dt_same_id matches synthetic periodic interval for a recurring CAN ID."""
    rows = [
        _make_frame(t=0.000, cid=0x100),
        _make_frame(t=0.005, cid=0x200),
        _make_frame(t=0.020, cid=0x100),  # dt_same_id = 0.020
        _make_frame(t=0.040, cid=0x100),  # dt_same_id = 0.020
        _make_frame(t=0.060, cid=0x100),  # dt_same_id = 0.020
    ]
    df = cast_canonical_df(pd.DataFrame(rows))
    feat_df, _ = build_feature_dataframe(df)

    dt_same = feat_df["dt_same_id"].to_numpy()
    assert dt_same[0] == 0.0  # first appearance
    assert dt_same[1] == 0.0  # first appearance of 0x200
    assert np.isclose(dt_same[2], 0.020)
    assert np.isclose(dt_same[3], 0.020)
    assert np.isclose(dt_same[4], 0.020)


def test_id_repetition_count_in_range_1_to_50():
    """Verify id_repetition_count is strictly within [1, 50] across bursts."""
    # Blast 70 consecutive frames of the same ID
    rows = [_make_frame(t=i * 0.0001, cid=0x000) for i in range(70)]
    df = cast_canonical_df(pd.DataFrame(rows))
    feat_df, _ = build_feature_dataframe(df)

    rep_counts = feat_df["id_repetition_count"].to_numpy()
    assert (rep_counts >= 1.0).all()
    assert (rep_counts <= 50.0).all()
    # At frame 55, window of last 50 has 50 identical IDs
    assert rep_counts[55] == 50.0


def test_state_resets_at_capture_boundary():
    """Verify state resets at capture boundary (Rule 5)."""
    rows = [
        _make_frame(t=0.0, cid=0x100, capture="cap_A"),
        _make_frame(t=0.1, cid=0x100, capture="cap_A"),
        _make_frame(t=0.0, cid=0x100, capture="cap_B"),  # Boundary transition
    ]
    df = cast_canonical_df(pd.DataFrame(rows))
    feat_df, _ = build_feature_dataframe(df)

    dt_same = feat_df["dt_same_id"].to_numpy()
    assert dt_same[0] == 0.0
    assert np.isclose(dt_same[1], 0.1)
    # At boundary, state resets so dt_same_id must be 0.0 again
    assert dt_same[2] == 0.0


def test_no_nan_or_inf_in_fixture_features():
    """Verify feature matrix on fixture dataset contains no NaNs or Infs."""
    raw_df = pd.read_csv(SAMPLES_DIR / "fixture.csv")
    df = cast_canonical_df(raw_df)

    X, y, baseline = build_feature_matrix(df)
    assert len(baseline.whitelist) > 0
    assert X.shape == (len(df), 20)
    assert y.shape == (len(df),)
    assert not np.isnan(X).any(), "NaN found in feature matrix!"
    assert not np.isinf(X).any(), "Inf found in feature matrix!"


def test_split_time_ordered_properties():
    """Verify split_time_ordered enforces 70/15/15 chronological partition."""
    raw_df = pd.read_csv(SAMPLES_DIR / "fixture.csv")
    df = cast_canonical_df(raw_df)

    train_df, val_df, test_df = split_time_ordered(df, 0.70, 0.15, 0.15)
    total_len = len(df)
    assert len(train_df) == int(total_len * 0.70)
    assert len(val_df) == int(total_len * 0.85) - len(train_df)
    assert len(train_df) + len(val_df) + len(test_df) == total_len

    # Strict time order: max train timestamp <= min val timestamp
    assert train_df["timestamp"].max() <= val_df["timestamp"].min()
    assert val_df["timestamp"].max() <= test_df["timestamp"].min()
