"""Tests for stark.pipeline â€” StreamingFeatures causality and DetectionPipeline results."""

from __future__ import annotations

from pathlib import Path

import pytest

from stark.pipeline.features import StreamingFeatures
from stark.pipeline.runner import DetectionPipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = REPO_ROOT / "data" / "samples"


# ============================================================================
# StreamingFeatures â€” causality tests
# ============================================================================


def test_streaming_features_dt_none_for_first_frame():
    """First frame with a given CAN ID must have dt_same_id == None."""
    sf = StreamingFeatures()
    result = sf.update({"timestamp": 1.0, "can_id": 0x100, "dlc": 8})
    assert result["dt_same_id"] is None


def test_streaming_features_dt_computed_for_second_frame():
    """dt_same_id is the difference between successive timestamps for same CAN ID."""
    sf = StreamingFeatures()
    sf.update({"timestamp": 1.000, "can_id": 0x100, "dlc": 8})
    result = sf.update({"timestamp": 1.020, "can_id": 0x100, "dlc": 8})
    assert result["dt_same_id"] == pytest.approx(0.020, abs=1e-6)


def test_streaming_features_dt_per_id_independent():
    """dt_same_id tracks each CAN ID independently â€” no cross-ID contamination."""
    sf = StreamingFeatures()
    sf.update({"timestamp": 0.0, "can_id": 0x100, "dlc": 8})
    sf.update({"timestamp": 0.5, "can_id": 0x200, "dlc": 8})  # different ID
    r = sf.update({"timestamp": 1.0, "can_id": 0x100, "dlc": 8})
    # dt should be 1.0 - 0.0 = 1.0, not 1.0 - 0.5
    assert r["dt_same_id"] == pytest.approx(1.0, abs=1e-6)


def test_streaming_features_msg_rate_50ms():
    """msg_rate_50ms counts frames in the trailing 50 ms bus-wide window."""
    sf = StreamingFeatures()
    # 3 frames, all within 50 ms
    sf.update({"timestamp": 0.000, "can_id": 0x100, "dlc": 8})
    sf.update({"timestamp": 0.010, "can_id": 0x200, "dlc": 8})
    r = sf.update({"timestamp": 0.020, "can_id": 0x300, "dlc": 8})
    assert r["msg_rate_50ms"] == 3

    # Frame far in the future â€” window should be 1
    r2 = sf.update({"timestamp": 1.000, "can_id": 0x100, "dlc": 8})
    assert r2["msg_rate_50ms"] == 1


def test_streaming_features_repetition_count():
    """id_repetition_count increments on identical consecutive payloads, resets otherwise."""
    sf = StreamingFeatures()
    payload = "AABB"
    r1 = sf.update({"timestamp": 0.0, "can_id": 0x100, "dlc": 2, "payload": payload})
    r2 = sf.update({"timestamp": 0.1, "can_id": 0x100, "dlc": 2, "payload": payload})
    r3 = sf.update({"timestamp": 0.2, "can_id": 0x100, "dlc": 2, "payload": payload})
    r4 = sf.update({"timestamp": 0.3, "can_id": 0x100, "dlc": 2, "payload": "CCDD"})
    assert r1["id_repetition_count"] == 1
    assert r2["id_repetition_count"] == 2
    assert r3["id_repetition_count"] == 3
    assert r4["id_repetition_count"] == 1  # reset on different payload


def test_streaming_features_hamming_none_first():
    """hamming_prev_same_id is None for the first frame of each CAN ID."""
    sf = StreamingFeatures()
    r = sf.update({"timestamp": 0.0, "can_id": 0x100, "dlc": 2, "payload": "FFFF"})
    assert r["hamming_prev_same_id"] is None


def test_streaming_features_hamming_distance():
    """hamming_prev_same_id gives correct bitwise Hamming distance."""
    sf = StreamingFeatures()
    sf.update({"timestamp": 0.0, "can_id": 0x100, "dlc": 1, "payload": "FF"})
    r = sf.update({"timestamp": 0.1, "can_id": 0x100, "dlc": 1, "payload": "00"})
    # 0xFF XOR 0x00 = 0xFF = 8 bits set
    assert r["hamming_prev_same_id"] == 8


def test_streaming_features_reset_clears_state():
    """reset() starts fresh â€” dt_same_id should be None again after reset."""
    sf = StreamingFeatures()
    sf.update({"timestamp": 0.0, "can_id": 0x100, "dlc": 8})
    sf.reset()
    r = sf.update({"timestamp": 1.0, "can_id": 0x100, "dlc": 8})
    assert r["dt_same_id"] is None


# ============================================================================
# DetectionPipeline â€” full integration tests
# ============================================================================


@pytest.fixture(scope="module")
def pipeline():
    """Build a DetectionPipeline from the fixture baseline once per module."""
    return DetectionPipeline.from_config(
        rules_yaml=str(REPO_ROOT / "config" / "rules.yaml"),
        baseline_csv=str(SAMPLES_DIR / "fixture.csv"),
    )


def test_pipeline_dos_sample_gives_alerts(pipeline):
    """demo_dos_attack.csv should produce alert_count > 0 with 'dos' labels."""
    import pandas as pd

    df = pd.read_csv(SAMPLES_DIR / "demo_dos_attack.csv", dtype={"CAN ID": str})
    frames = []
    for _, row in df.iterrows():
        can_id_raw = row.get("CAN ID") or row.get("can_id") or "0"
        ts = float(row.get("Timestamp") or row.get("timestamp") or 0.0)
        dlc = int(row.get("DLC") or row.get("dlc") or 0)
        byte_vals = []
        for i in range(8):
            v = row.get(f"DATA[{i}]")
            if v is not None and str(v).strip() not in ("", "nan"):
                try:
                    byte_vals.append(int(str(v).strip(), 16) & 0xFF)
                except ValueError:
                    pass
        payload = "".join(f"{b:02X}" for b in byte_vals)
        frames.append({"timestamp": ts, "can_id": str(can_id_raw), "dlc": dlc, "payload": payload})

    result = pipeline.run(frames)
    assert result["alert_count"] > 0, "DoS dataset should produce alerts"
    assert "dos" in result["by_label"], "DoS dataset should produce 'dos' label"


def test_pipeline_normal_sample_few_alerts(pipeline):
    """demo_normal.csv should produce <= 3% alert rate."""
    import pandas as pd

    df = pd.read_csv(SAMPLES_DIR / "demo_normal.csv", dtype={"CAN ID": str})
    frames = []
    for _, row in df.iterrows():
        can_id_raw = row.get("CAN ID") or row.get("can_id") or "0"
        ts = float(row.get("Timestamp") or row.get("timestamp") or 0.0)
        dlc = int(row.get("DLC") or row.get("dlc") or 0)
        byte_vals = []
        for i in range(8):
            v = row.get(f"DATA[{i}]")
            if v is not None and str(v).strip() not in ("", "nan"):
                try:
                    byte_vals.append(int(str(v).strip(), 16) & 0xFF)
                except ValueError:
                    pass
        payload = "".join(f"{b:02X}" for b in byte_vals)
        frames.append({"timestamp": ts, "can_id": str(can_id_raw), "dlc": dlc, "payload": payload})

    result = pipeline.run(frames)
    total = result["total_frames"]
    alert_rate = result["alert_count"] / total if total > 0 else 0.0
    assert alert_rate <= 0.03, (
        f"Normal dataset alert rate {alert_rate:.2%} exceeds 3% threshold "
        f"({result['alert_count']}/{total} alerts)"
    )


def test_streaming_features_corrupted_inputs():
    """StreamingFeatures handles malformed, NaN, and non-numeric inputs without crashing."""
    sf = StreamingFeatures()

    # Corrupt string timestamp -> should gracefully become None
    r1 = sf.update({"timestamp": "INVALID_TS", "can_id": "0x140", "dlc": "8"})
    assert r1["dt_same_id"] is None
    assert r1["can_id"] == 0x140
    assert r1["dlc"] == 8

    # Float NaN timestamp -> should gracefully become None
    r2 = sf.update({"timestamp": float("nan"), "can_id": "0x140", "dlc": 8})
    assert r2["dt_same_id"] is None

    # Empty payload, missing fields
    r3 = sf.update({})
    assert r3["can_id"] == 0
    assert r3["dlc"] == 0
    assert r3["dt_same_id"] is None


def test_pipeline_ground_truth_dos_accuracy(pipeline):
    """Verify exact recall on demo_dos_attack.csv: all 100 Flag==T frames detected."""
    import pandas as pd

    df = pd.read_csv(SAMPLES_DIR / "demo_dos_attack.csv", dtype={"CAN ID": str})
    frames = []
    for _, row in df.iterrows():
        frames.append({
            "timestamp": float(row["Timestamp"]),
            "can_id": str(row["CAN ID"]),
            "dlc": int(row["DLC"]),
            "payload": "".join(f"{int(row[f'DATA[{i}]'], 16):02X}" for i in range(8)),
        })

    res = pipeline.run(frames)
    assert res["total_frames"] == 300
    assert res["alert_count"] == 100
    assert res["normal_count"] == 200
    assert res["by_label"].get("dos") == 100
    assert res["by_label"].get("normal") == 200


def test_pipeline_ground_truth_normal_cleanliness(pipeline):
    """Verify zero false alarms on demo_normal.csv."""
    import pandas as pd

    df = pd.read_csv(SAMPLES_DIR / "demo_normal.csv", dtype={"CAN ID": str})
    frames = []
    for _, row in df.iterrows():
        frames.append({
            "timestamp": float(row["Timestamp"]),
            "can_id": str(row["CAN ID"]),
            "dlc": int(row["DLC"]),
            "payload": "".join(f"{int(row[f'DATA[{i}]'], 16):02X}" for i in range(8)),
        })

    res = pipeline.run(frames)
    assert res["total_frames"] == 300
    assert res["normal_count"] == 300
    assert res["alert_count"] == 0
    assert res["by_label"] == {"normal": 300}
