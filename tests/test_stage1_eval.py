"""Unit tests for Stage 1 standalone evaluation (scripts/eval_stage1_only.py).

Verifies:
- Threshold rebuilding strictly from training split normal frames
- Standalone RuleEngine evaluation on synthetic frame sets
- Presence of all required evaluation metrics and keys
- FPR bounded within [0, 1]
- Confusion matrix and filtering rate consistency
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure project root is in sys.path so scripts can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.eval_stage1_only import (  # noqa: E402
    evaluate_stage1_dataset,
    load_dataset_splits,
    rebuild_stage1_engine,
)


@pytest.fixture
def tiny_synthetic_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create a minimal synthetic train and validation frame set."""
    train_rows = [
        # Normal frames from authorized IDs (0x140 and 0x260)
        {"timestamp": 0.010, "can_id": "0140", "dlc": 8, "data[0]": "00", "flag": "R"},
        {"timestamp": 0.020, "can_id": "0140", "dlc": 8, "data[0]": "01", "flag": "R"},
        {"timestamp": 0.030, "can_id": "0140", "dlc": 8, "data[0]": "02", "flag": "R"},
        {"timestamp": 0.040, "can_id": "0260", "dlc": 8, "data[0]": "AA", "flag": "R"},
        {"timestamp": 0.050, "can_id": "0140", "dlc": 8, "data[0]": "03", "flag": "R"},
        {"timestamp": 0.060, "can_id": "0260", "dlc": 8, "data[0]": "BB", "flag": "R"},
        {"timestamp": 0.070, "can_id": "0140", "dlc": 8, "data[0]": "04", "flag": "R"},
        {"timestamp": 0.080, "can_id": "0260", "dlc": 8, "data[0]": "CC", "flag": "R"},
    ]
    train_df = pd.DataFrame(train_rows)

    val_rows = [
        # 1. Normal clean frame (authorized 0x140, expected DLC 8)
        {"timestamp": 0.090, "can_id": "0140", "dlc": 8, "data[0]": "05", "flag": "R"},
        # 2. Normal clean frame (authorized 0x260, expected DLC 8)
        {"timestamp": 0.100, "can_id": "0260", "dlc": 8, "data[0]": "DD", "flag": "R"},
        # 3. Attack frame: Unknown ID (0x999) -> triggers R1 VIOLATION
        {"timestamp": 0.110, "can_id": "0999", "dlc": 8, "data[0]": "EE", "flag": "T"},
        # 4. Attack frame: DLC violation (authorized 0x140, DLC 4 != 8) -> triggers R4 SUSPECT
        {"timestamp": 0.120, "can_id": "0140", "dlc": 4, "data[0]": "FF", "flag": "T"},
    ]
    val_df = pd.DataFrame(val_rows)

    return train_df, val_df


def test_rebuild_stage1_engine(tiny_synthetic_data):
    """Verify that rebuild_stage1_engine fits the profiler and configures RuleEngine."""
    train_df, _ = tiny_synthetic_data
    engine, profiler, cfg = rebuild_stage1_engine(train_df, rules_yaml_path=None)

    assert 0x140 in profiler.id_whitelist
    assert 0x260 in profiler.id_whitelist
    assert 0x999 not in profiler.id_whitelist
    assert "global_tuned_thresholds" in cfg
    assert "r3_global_rate" in cfg["global_tuned_thresholds"]


def test_evaluate_stage1_core_metrics(tiny_synthetic_data):
    """Verify Stage 1 standalone evaluation produces all required keys and valid FPR."""
    train_df, val_df = tiny_synthetic_data
    engine, _, _ = rebuild_stage1_engine(train_df, rules_yaml_path=None)

    metrics = evaluate_stage1_dataset(val_df, engine)

    # 1. Verify required top-level keys exist
    expected_keys = {
        "total_frames",
        "clean_frames",
        "flagged_frames",
        "confusion_matrix",
        "precision",
        "recall",
        "fpr",
        "f1_score",
        "filtering_rate",
        "latency_ms",
        "verdict_breakdown",
        "rule_hits",
        "per_attack_recall",
    }
    assert expected_keys.issubset(metrics.keys())

    # 2. Verify confusion matrix keys
    cm = metrics["confusion_matrix"]
    for k in ("tp", "fp", "tn", "fn"):
        assert k in cm
        assert isinstance(cm[k], int)

    # 3. Check FPR is strictly bounded in [0, 1]
    assert 0.0 <= metrics["fpr"] <= 1.0

    # 4. Check Precision, Recall, and Filtering Rate bounds
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    assert 0.0 <= metrics["filtering_rate"] <= 1.0

    # 5. Check latency dictionary
    lat = metrics["latency_ms"]
    for l_key in ("median", "mean", "p95", "p99"):
        assert l_key in lat
        assert lat[l_key] >= 0.0

    # 6. Verify arithmetic consistency
    assert cm["tp"] + cm["fp"] + cm["tn"] + cm["fn"] == metrics["total_frames"]
    assert (
        metrics["clean_frames"] + metrics["flagged_frames"] == metrics["total_frames"]
    )
    assert metrics["clean_frames"] == cm["tn"] + cm["fn"]
    assert metrics["flagged_frames"] == cm["tp"] + cm["fp"]

    # 7. In our synthetic test:
    # 2 attacks (0x999 and DLC mismatch) both get flagged (TP=2, FN=0 -> Recall=1.0)
    # 2 normal frames are both compliant (FP=0, TN=2 -> FPR=0.0)
    assert cm["tp"] == 2
    assert cm["fn"] == 0
    assert cm["fp"] == 0
    assert cm["tn"] == 2
    assert metrics["recall"] == 1.0
    assert metrics["precision"] == 1.0
    assert metrics["fpr"] == 0.0


def test_load_dataset_splits_fallback():
    """Verify fallback split loading yields time-ordered 70/15 partition."""
    train_df, val_df, is_fixture, desc = load_dataset_splits()

    assert len(train_df) > 0
    assert len(val_df) > 0
    # In fixture.csv (4081 rows), 70% is 2856 and 15% is 612
    assert len(train_df) == 2856
    assert len(val_df) == 612
    assert is_fixture is True
    assert "fixture" in desc.lower()
