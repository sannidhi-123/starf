"""Unit tests for STARK Stage 1 BaselineProfiler (src/stark/baseline/profiler.py)."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from stark.baseline.profiler import BaselineProfiler


@pytest.fixture
def fixture_csv_path() -> Path:
    """Return path to data/samples/fixture.csv."""
    path = Path("data/samples/fixture.csv")
    if not path.exists():
        # Fallback if pytest runs in another cwd
        path = (
            Path(__file__).resolve().parent.parent / "data" / "samples" / "fixture.csv"
        )
    assert path.exists(), f"Fixture file not found at: {path}"
    return path


def test_baseline_profiler_fit_on_fixture(fixture_csv_path: Path):
    """Test profiler fitting on real fixture data.

    Asserts:
    - Normal frames ('R') are isolated from attack injections ('T')
    - Known periodic ID satisfies p01_dt < p99_dt
    - Whitelist contains normal IDs and excludes attack ID 0
    - modal_dlc, is_periodic, repetition, and hamming stats are within expected bounds
    """
    df = pd.read_csv(fixture_csv_path)
    profiler = BaselineProfiler()
    profiler.fit(df)

    # 1. Whitelist verification
    # Attack injection uses ID 0 (Flag 'T') which must NOT be present in normal whitelist
    assert 0 not in profiler.id_whitelist
    # Normal IDs present in fixture
    expected_ids = {140, 260, 316, 329, 430, 545}
    assert expected_ids.issubset(set(profiler.id_whitelist))

    # 2. Known periodic ID verification (ID 140 / 0x0140: nominal 10ms cycle)
    known_id = 140
    assert known_id in profiler.p01_dt
    p01 = profiler.p01_dt[known_id]
    p99 = profiler.p99_dt[known_id]

    # Required specification assertion: p01_dt < p99_dt
    assert p01 < p99
    # Nominal ~10 ms (0.010 s) with ~1 ms jitter bounds
    assert 0.008 < p01 < 0.010
    assert 0.010 < p99 < 0.012

    # Periodicity check
    assert profiler.is_periodic[known_id] is True

    # Modal DLC check
    assert profiler.modal_dlc[known_id] == 8

    # Repetition percentile
    assert profiler.p995_rep[known_id] >= 1.0

    # Hamming distance percentile (in [0, 64] bits)
    assert 0.0 <= profiler.p99_hamming[known_id] <= 64.0


def test_baseline_profiler_save_load_roundtrip_yaml(
    fixture_csv_path: Path, tmp_path: Path
):
    """Test save() then load() round-trip with YAML format."""
    df = pd.read_csv(fixture_csv_path)
    profiler = BaselineProfiler()
    profiler.fit(df)

    yaml_file = tmp_path / "baseline_roundtrip.yaml"
    profiler.save(yaml_file)
    assert yaml_file.exists()

    # Class-method load
    loaded = BaselineProfiler.load(yaml_file)

    # Verify all baseline fields round-trip exactly
    assert loaded.id_whitelist == profiler.id_whitelist
    assert loaded.modal_dlc == profiler.modal_dlc
    assert loaded.is_periodic == profiler.is_periodic
    assert loaded.p01_dt == profiler.p01_dt
    assert loaded.p99_dt == profiler.p99_dt
    assert loaded.p995_rep == profiler.p995_rep
    assert loaded.p99_hamming == profiler.p99_hamming

    # Verify lookups on loaded profiler work with hex and decimal
    assert loaded.p01_dt[140] < loaded.p99_dt[140]
    assert loaded.p01_dt["0x0140"] == profiler.p01_dt[140]


def test_baseline_profiler_save_load_roundtrip_json(
    fixture_csv_path: Path, tmp_path: Path
):
    """Test save() then load() round-trip with JSON format."""
    df = pd.read_csv(fixture_csv_path)
    profiler = BaselineProfiler()
    profiler.fit(df)

    json_file = tmp_path / "baseline_roundtrip.json"
    profiler.save(json_file)
    assert json_file.exists()

    # Instance-method load
    loaded = BaselineProfiler().load(json_file)

    assert loaded.id_whitelist == profiler.id_whitelist
    assert loaded.modal_dlc == profiler.modal_dlc
    assert loaded.is_periodic == profiler.is_periodic
    assert loaded.p01_dt == profiler.p01_dt
    assert loaded.p99_dt == profiler.p99_dt
    assert loaded.p995_rep == profiler.p995_rep
    assert loaded.p99_hamming == profiler.p99_hamming


def test_baseline_profiler_precomputed_features():
    """Test that precomputed feature columns (Person 1's FeatureState schema) are respected."""
    # Synthetic dataset with precomputed features
    df = pd.DataFrame(
        {
            "can_id": [0x140] * 10,
            "timestamp": [i * 0.01 for i in range(10)],
            "dt_same_id": [0.01] * 10,
            "id_repetition_count": [1, 2, 3, 1, 2, 1, 1, 1, 2, 1],
            "hamming_prev_same_id": [0, 4, 8, 2, 6, 12, 14, 0, 4, 8],
            "dlc": [8] * 10,
        }
    )

    profiler = BaselineProfiler().fit(df)

    assert profiler.id_whitelist == [0x140]
    assert profiler.p01_dt[0x140] == 0.01
    assert profiler.p99_dt[0x140] == 0.01
    assert profiler.is_periodic[0x140] is True
    assert profiler.modal_dlc[0x140] == 8
    assert profiler.p995_rep[0x140] == pytest.approx(
        np.percentile([1, 2, 3, 1, 2, 1, 1, 1, 2, 1], 99.5)
    )
    assert profiler.p99_hamming[0x140] == pytest.approx(
        np.percentile([0, 4, 8, 2, 6, 12, 14, 0, 4, 8], 99.0)
    )


def test_baseline_profiler_aperiodic_classification():
    """Test that an event-driven ID with high inter-arrival jitter is flagged as is_periodic=False."""
    # Aperiodic timestamps with erratic gaps: 0.01, 1.5, 0.02, 5.0, 0.01, 10.0
    timestamps = [0.0, 0.01, 1.51, 1.53, 6.53, 6.54, 16.54, 16.55]
    df = pd.DataFrame(
        {
            "can_id": [0x220] * len(timestamps),
            "timestamp": timestamps,
            "dlc": [4] * len(timestamps),
            "payload": ["01020304"] * len(timestamps),
        }
    )

    profiler = BaselineProfiler(cv_threshold=0.30).fit(df)
    assert profiler.is_periodic[0x220] is False


def test_baseline_profiler_empty_dataframe():
    """Test that an empty DataFrame raises ValueError."""
    profiler = BaselineProfiler()
    with pytest.raises(
        ValueError, match="Cannot fit BaselineProfiler on empty DataFrame"
    ):
        profiler.fit(pd.DataFrame())
