#!/usr/bin/env python3
"""Evaluate Stage 1 RuleEngine standalone on validation split.

Measures Stage 1 deterministic rule evaluation in isolation (no ML):
- Loads validation split (from Person 1 if available in src/stark/data/split.py
  or data/processed/, otherwise falls back to fixture with time-ordered 70/15/15 split).
- Rebuilds thresholds strictly from the TRAIN split's normal frames only.
- Evaluates RuleEngine on every VALIDATION frame.
- Reports precision, recall, FPR, confusion counts (TP, FP, TN, FN),
  per-attack-type recall (where labels permit), filtering rate (CLEAN share),
  and median per-frame latency in ms.
- Outputs summary table and writes reports/stage1_only_metrics.json.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

# Ensure src/ and repo root are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from stark.baseline.profiler import BaselineProfiler  # noqa: E402
from stark.rules.definitions import (  # noqa: E402
    FEATURE_CAN_ID,
    FEATURE_DELTA_T,
    FEATURE_DLC,
    FEATURE_HAMMING_DISTANCE,
    FEATURE_MSG_RATE_50MS,
    FEATURE_REPETITION_COUNT,
)
from stark.rules.engine import RuleEngine  # noqa: E402


def calculate_50ms_message_count_p999(
    df: pd.DataFrame,
    time_col: str,
) -> float:
    """Compute the 99.9th percentile of total bus message count in trailing 50ms windows.

    Args:
        df: DataFrame containing normal traffic frames.
        time_col: Name of timestamp column in seconds.

    Returns:
        float: 99.9th percentile message count in a 50ms window.
    """
    timestamps = df[time_col].sort_values().values
    if len(timestamps) == 0:
        return 0.0
    left_indices = np.searchsorted(timestamps, timestamps - 0.050, side="left")
    counts = np.arange(len(timestamps)) - left_indices + 1
    return float(np.percentile(counts, 99.9))


def resolve_column(
    df: pd.DataFrame,
    candidates: List[str],
    required: bool = False,
) -> Optional[str]:
    """Resolve DataFrame column case-insensitively from candidates."""
    cols_map = {str(c).lower().strip(): c for c in df.columns}
    for cand in candidates:
        cand_clean = cand.lower().strip()
        if cand_clean in cols_map:
            return cols_map[cand_clean]
    if required:
        raise ValueError(
            f"Required column not found. Candidates {candidates} not in {list(df.columns)}"
        )
    return None


def filter_normal_frames(df: pd.DataFrame) -> Tuple[pd.DataFrame, Optional[str]]:
    """Filter DataFrame to normal frames only based on flag/label column.

    Returns:
        Tuple of (normal_df, flag_col_name).
    """
    flag_col = resolve_column(
        df,
        ["flag", "label", "status", "attack", "is_attack", "class"],
        required=False,
    )
    if flag_col is None:
        return df.copy(), None

    unique_vals = set(df[flag_col].dropna().unique())
    # Car-Hacking convention: 'R' is Regular (normal), 'T' is Tampered (attack)
    if "R" in unique_vals:
        return df[df[flag_col] == "R"].copy(), flag_col
    if "normal" in unique_vals:
        return df[df[flag_col] == "normal"].copy(), flag_col
    if 0 in unique_vals and 1 in unique_vals:
        return df[df[flag_col] == 0].copy(), flag_col

    return df.copy(), flag_col


def is_attack_frame(val: Any) -> bool:
    """Determine whether a flag/label value signifies an attack frame."""
    if pd.isna(val):
        return False
    if isinstance(val, (int, np.integer)):
        return int(val) != 0
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    val_str = str(val).strip().upper()
    if val_str in (
        "T",
        "1",
        "ATTACK",
        "ANOMALY",
        "TRUE",
        "DOS",
        "FUZZY",
        "SPOOFING",
        "REPLAY",
    ):
        return True
    if val_str in ("R", "0", "NORMAL", "BENIGN", "FALSE", "CLEAN"):
        return False
    # Any other specific attack name
    return True


def parse_can_id(val: Any) -> int:
    """Parse CAN ID string or int to canonical integer."""
    if isinstance(val, (int, np.integer)):
        return int(val)
    s = str(val).strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    # Check if standard hex string without 0x prefix
    try:
        return int(s, 16)
    except ValueError:
        return int(s)


def extract_payload_bytes_from_row(row: Any, data_cols: List[str]) -> bytes:
    """Extract payload bytes from a row series or dict."""
    if "payload" in row and pd.notna(row["payload"]):
        p = row["payload"]
        if isinstance(p, (bytes, bytearray)):
            return bytes(p)
        if isinstance(p, str):
            clean = p.replace(" ", "").replace("0x", "").strip()
            try:
                return bytes.fromhex(clean)
            except ValueError:
                return clean.encode("utf-8")

    byte_vals: List[int] = []
    for c in data_cols:
        v = row.get(c) if isinstance(row, dict) else row[c] if c in row else None
        if v is None or pd.isna(v):
            continue
        if isinstance(v, (int, np.integer)):
            byte_vals.append(int(v) & 0xFF)
        elif isinstance(v, str):
            v_clean = v.strip()
            if v_clean:
                try:
                    byte_vals.append(int(v_clean, 16))
                except ValueError:
                    pass
    return bytes(byte_vals)


def calculate_bitwise_hamming(b1: bytes, b2: bytes) -> int:
    """Compute bitwise Hamming distance between two byte payloads."""
    common_len = min(len(b1), len(b2))
    dist = sum((x ^ y).bit_count() for x, y in zip(b1[:common_len], b2[:common_len]))
    dist += abs(len(b1) - len(b2)) * 8
    return dist


def load_dataset_splits(
    data_override: Optional[Path] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, bool, str]:
    """Load train and validation splits.

    Checks:
    1. Person 1 split module (`src/stark/data/split.py` / `stark.data.split`)
    2. Processed split files in `data/processed/`
    3. Fallback: `data/samples/fixture.csv` (time-ordered 70/15/15 split, never shuffled)

    Returns:
        Tuple of (train_df, val_df, is_synthetic_fixture, source_description).
    """
    if data_override is not None:
        p = Path(data_override)
        if not p.exists():
            raise FileNotFoundError(f"Data file not found: {p}")
        df = pd.read_csv(p, dtype={"CAN ID": str, "can_id": str})
        time_col = resolve_column(df, ["timestamp", "time", "ts"], required=True)
        assert time_col is not None
        df = df.sort_values(by=time_col).reset_index(drop=True)
        n = len(df)
        train_df = df.iloc[: int(0.70 * n)].copy()
        val_df = df.iloc[int(0.70 * n) : int(0.85 * n)].copy()
        is_fixture = "fixture" in str(p).lower()
        return train_df, val_df, is_fixture, f"Custom dataset: {p}"

    # 1. Try importing Person 1's split module if present
    try:
        split_mod = importlib.import_module("stark.data.split")
        for fn_name in ["load_validation_split", "load_splits", "get_splits"]:
            if hasattr(split_mod, fn_name):
                fn = getattr(split_mod, fn_name)
                res = fn()
                if isinstance(res, tuple) and len(res) >= 2:
                    return res[0], res[1], False, "Person 1 stark.data.split module"
                if isinstance(res, dict) and "val" in res and "train" in res:
                    return (
                        res["train"],
                        res["val"],
                        False,
                        "Person 1 stark.data.split module",
                    )
    except (ImportError, ModuleNotFoundError, AttributeError):
        pass

    # 2. Try loading from data/processed/
    proc_dir = Path("data/processed")
    val_candidates = ["val.csv", "validation.csv", "val.parquet", "validation.parquet"]
    train_candidates = ["train.csv", "train.parquet"]
    found_val = None
    found_train = None
    if proc_dir.exists():
        for c in val_candidates:
            if (proc_dir / c).exists():
                found_val = proc_dir / c
                break
        for c in train_candidates:
            if (proc_dir / c).exists():
                found_train = proc_dir / c
                break

    if found_val is not None and found_train is not None:
        read_fn = pd.read_parquet if found_val.suffix == ".parquet" else pd.read_csv
        val_df = read_fn(found_val)
        train_df = read_fn(found_train)
        return train_df, val_df, False, f"Processed split: {found_val.name}"

    # 3. Fallback: data/samples/fixture.csv with time-ordered 70/15/15 split
    fixture_path = Path("data/samples/fixture.csv")
    if not fixture_path.exists():
        raise FileNotFoundError(
            f"Neither Person 1 split nor fixture found at {fixture_path}"
        )

    df = pd.read_csv(fixture_path, dtype={"CAN ID": str, "can_id": str})
    time_col = resolve_column(df, ["timestamp", "time", "ts"], required=True)
    assert time_col is not None
    df = df.sort_values(by=time_col).reset_index(drop=True)
    n = len(df)
    train_df = df.iloc[: int(0.70 * n)].copy()
    val_df = df.iloc[int(0.70 * n) : int(0.85 * n)].copy()

    return (
        train_df,
        val_df,
        True,
        f"Synthetic fixture fallback ({fixture_path}, time-ordered 70/15 split)",
    )


def rebuild_stage1_engine(
    train_df: pd.DataFrame,
    rules_yaml_path: Optional[Path] = Path("config/rules.yaml"),
) -> Tuple[RuleEngine, BaselineProfiler, Dict[str, Any]]:
    """Rebuild Stage 1 thresholds from TRAIN split normal frames only.

    Args:
        train_df: Training split DataFrame.
        rules_yaml_path: Optional path to rules.yaml base configuration.

    Returns:
        Tuple of (configured RuleEngine, fitted BaselineProfiler, config dict).
    """
    normal_train_df, _ = filter_normal_frames(train_df)
    if normal_train_df.empty:
        raise ValueError("TRAIN split contains no normal frames to fit thresholds!")

    profiler = BaselineProfiler()
    profiler.fit(normal_train_df)

    time_col = resolve_column(
        normal_train_df, ["timestamp", "time", "ts"], required=True
    )
    assert time_col is not None
    r3_global_rate = calculate_50ms_message_count_p999(
        normal_train_df, time_col=time_col
    )

    # Load base config if available to preserve factors and default parameters
    cfg: Dict[str, Any] = {}
    if rules_yaml_path is not None and Path(rules_yaml_path).exists():
        with open(rules_yaml_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                cfg = loaded

    cfg.setdefault("global_tuned_thresholds", {})
    cfg["global_tuned_thresholds"].setdefault("r2_factor", 0.5)
    cfg["global_tuned_thresholds"]["r3_global_rate"] = r3_global_rate
    cfg["global_tuned_thresholds"].setdefault("r7_factor", 5.0)
    cfg["global_tuned_thresholds"].setdefault("physical_min_dt", 0.00020)
    cfg["global_tuned_thresholds"].setdefault("modal_dlc_default", 8)
    cfg["global_tuned_thresholds"].setdefault("default_max_repetition", 5)
    cfg["global_tuned_thresholds"].setdefault("default_max_hamming", 48)

    cfg.setdefault("per_id_baselines", {})
    cfg["per_id_baselines"]["id_whitelist"] = [int(i) for i in profiler.id_whitelist]
    cfg["per_id_baselines"]["modal_dlc"] = {
        int(k): int(v) for k, v in profiler.modal_dlc.items()
    }
    cfg["per_id_baselines"]["p01_dt"] = {
        int(k): float(v) for k, v in profiler.p01_dt.items()
    }
    cfg["per_id_baselines"]["p99_dt"] = {
        int(k): float(v) for k, v in profiler.p99_dt.items()
    }
    cfg["per_id_baselines"]["p995_rep"] = {
        int(k): float(v) for k, v in profiler.p995_rep.items()
    }
    cfg["per_id_baselines"]["p99_hamming"] = {
        int(k): float(v) for k, v in profiler.p99_hamming.items()
    }
    cfg["per_id_baselines"]["is_periodic"] = {
        int(k): bool(v) for k, v in profiler.is_periodic.items()
    }

    engine = RuleEngine(cfg=cfg, profile=profiler)
    return engine, profiler, cfg


def evaluate_stage1_dataset(
    val_df: pd.DataFrame,
    engine: RuleEngine,
) -> Dict[str, Any]:
    """Evaluate RuleEngine on validation dataset and compute standalone metrics.

    Args:
        val_df: Validation split DataFrame.
        engine: Configured RuleEngine.

    Returns:
        Dictionary of computed Stage 1 evaluation metrics.
    """
    id_col = resolve_column(
        val_df,
        ["can_id", "can id", "canid", "id", "arbitration_id"],
        required=True,
    )
    assert id_col is not None

    dlc_col = resolve_column(val_df, ["dlc", "data_length_code"], required=False)
    time_col = resolve_column(val_df, ["timestamp", "time", "ts"], required=False)

    flag_col = resolve_column(
        val_df,
        ["flag", "label", "status", "attack", "is_attack", "class"],
        required=False,
    )

    # Check for precomputed feature columns
    dt_col = resolve_column(
        val_df, ["dt_same_id", "delta_t", "dt", "time_delta"], required=False
    )
    rate_col = resolve_column(
        val_df, ["msg_rate_50ms", "msg_count_50ms", "bus_rate"], required=False
    )
    rep_col = resolve_column(
        val_df,
        ["id_repetition_count", "repetition_count", "repetition", "rep_count"],
        required=False,
    )
    ham_col = resolve_column(
        val_df,
        ["hamming_prev_same_id", "hamming_distance", "hamming_prev", "hamming"],
        required=False,
    )

    # Payload columns for raw frames
    data_cols: List[str] = []
    for i in range(8):
        c = resolve_column(val_df, [f"data[{i}]", f"data_{i}", f"d{i}"], required=False)
        if c is not None:
            data_cols.append(c)

    # Causal streaming state tracking for raw frames
    last_seen_time: Dict[int, float] = {}
    last_payload: Dict[int, bytes] = {}
    rep_counts: Dict[int, int] = {}
    sliding_window_ts: List[float] = []

    tp = 0
    fp = 0
    tn = 0
    fn = 0
    clean_count = 0
    flagged_count = 0

    rule_hits: Dict[str, int] = {
        "R1": 0,
        "R2": 0,
        "R3": 0,
        "R4": 0,
        "R5": 0,
        "R6": 0,
        "R7": 0,
    }
    verdict_counts: Dict[str, int] = {"VIOLATION": 0, "SUSPECT": 0, "CLEAN": 0}

    # Per-attack-type metrics
    attack_totals: Dict[str, int] = {}
    attack_detected: Dict[str, int] = {}

    latencies_ms: List[float] = []

    total_frames = len(val_df)

    for _, row in val_df.iterrows():
        raw_id = row[id_col]
        can_id = parse_can_id(raw_id)
        dlc = int(row[dlc_col]) if dlc_col is not None and pd.notna(row[dlc_col]) else 8

        # Ground truth
        is_attack = False
        attack_type = "unknown"
        if flag_col is not None and pd.notna(row[flag_col]):
            raw_flag = row[flag_col]
            is_attack = is_attack_frame(raw_flag)
            if is_attack:
                attack_type = str(raw_flag).strip()
                attack_totals[attack_type] = attack_totals.get(attack_type, 0) + 1

        # Causal feature extraction
        frame: Dict[str, Any] = {
            FEATURE_CAN_ID: can_id,
            FEATURE_DLC: dlc,
        }

        # 1. dt_same_id
        if dt_col is not None and pd.notna(row[dt_col]):
            frame[FEATURE_DELTA_T] = float(row[dt_col])
        elif time_col is not None and pd.notna(row[time_col]):
            t_curr = float(row[time_col])
            if can_id in last_seen_time:
                frame[FEATURE_DELTA_T] = t_curr - last_seen_time[can_id]
            else:
                frame[FEATURE_DELTA_T] = None
            last_seen_time[can_id] = t_curr

        # 2. msg_rate_50ms
        if rate_col is not None and pd.notna(row[rate_col]):
            frame[FEATURE_MSG_RATE_50MS] = float(row[rate_col])
        elif time_col is not None and pd.notna(row[time_col]):
            t_curr = float(row[time_col])
            sliding_window_ts.append(t_curr)
            # Evict timestamps older than 50ms (0.050s)
            cutoff = t_curr - 0.050
            while sliding_window_ts and sliding_window_ts[0] < cutoff:
                sliding_window_ts.pop(0)
            frame[FEATURE_MSG_RATE_50MS] = len(sliding_window_ts)

        # Extract payload bytes for R5 repetition and R6 Hamming
        p_bytes = extract_payload_bytes_from_row(row, data_cols)

        # 3. id_repetition_count
        if rep_col is not None and pd.notna(row[rep_col]):
            frame[FEATURE_REPETITION_COUNT] = float(row[rep_col])
        else:
            if can_id in last_payload and last_payload[can_id] == p_bytes:
                rep_counts[can_id] = rep_counts.get(can_id, 1) + 1
            else:
                rep_counts[can_id] = 1
            frame[FEATURE_REPETITION_COUNT] = rep_counts[can_id]

        # 4. hamming_prev_same_id
        if ham_col is not None and pd.notna(row[ham_col]):
            frame[FEATURE_HAMMING_DISTANCE] = float(row[ham_col])
        else:
            if can_id in last_payload:
                frame[FEATURE_HAMMING_DISTANCE] = calculate_bitwise_hamming(
                    p_bytes, last_payload[can_id]
                )
            else:
                frame[FEATURE_HAMMING_DISTANCE] = None

        last_payload[can_id] = p_bytes

        # Timed evaluation
        t_start = time.perf_counter()
        verdict = engine.evaluate(frame)
        t_elapsed = (time.perf_counter() - t_start) * 1000.0  # ms
        latencies_ms.append(t_elapsed)

        # Aggregate verdicts and hits
        v_str = verdict.verdict
        verdict_counts[v_str] = verdict_counts.get(v_str, 0) + 1
        for hit in verdict.hits:
            rule_hits[hit.rule_id] = rule_hits.get(hit.rule_id, 0) + 1

        is_flagged = v_str in ("VIOLATION", "SUSPECT")
        if is_flagged:
            flagged_count += 1
            if is_attack:
                tp += 1
                attack_detected[attack_type] = attack_detected.get(attack_type, 0) + 1
            else:
                fp += 1
        else:
            clean_count += 1
            if is_attack:
                fn += 1
            else:
                tn += 1

    # Metrics computation
    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    f1 = (
        float(2 * precision * recall / (precision + recall))
        if (precision + recall) > 0
        else 0.0
    )
    filtering_rate = float(clean_count / total_frames) if total_frames > 0 else 0.0

    latency_array = np.array(latencies_ms) if latencies_ms else np.array([0.0])
    median_latency = float(np.median(latency_array))
    mean_latency = float(np.mean(latency_array))
    p95_latency = float(np.percentile(latency_array, 95.0))
    p99_latency = float(np.percentile(latency_array, 99.0))

    per_attack_recall = {}
    for att, tot in attack_totals.items():
        det = attack_detected.get(att, 0)
        per_attack_recall[att] = {
            "total": tot,
            "detected": det,
            "recall": float(det / tot) if tot > 0 else 0.0,
        }

    return {
        "total_frames": total_frames,
        "clean_frames": clean_count,
        "flagged_frames": flagged_count,
        "confusion_matrix": {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
        },
        "precision": precision,
        "recall": recall,
        "fpr": fpr,
        "f1_score": f1,
        "filtering_rate": filtering_rate,
        "latency_ms": {
            "median": median_latency,
            "mean": mean_latency,
            "p95": p95_latency,
            "p99": p99_latency,
        },
        "verdict_breakdown": verdict_counts,
        "rule_hits": rule_hits,
        "per_attack_recall": per_attack_recall,
    }


def format_table(results: Dict[str, Any], meta: Dict[str, Any]) -> str:
    """Format evaluation results into a clean ASCII table."""
    cm = results["confusion_matrix"]
    lat = results["latency_ms"]

    lines = [
        "=" * 68,
        "  STARF Detection Pipeline - Stage 1 Standalone Evaluation Report",
        "=" * 68,
        f"Data Source:        {meta.get('source_desc', 'Unknown')}",
        f"Data Category:      {'SYNTHETIC FIXTURE' if meta.get('is_fixture') else 'REAL BENCHMARK'}",
        f"TRAIN Split Frames: {meta.get('train_frames', 'N/A')} ({meta.get('train_normal_frames', 'N/A')} normal frames)",
        f"VAL Split Frames:   {results['total_frames']} ({cm['tp'] + cm['fn']} attacks, {cm['fp'] + cm['tn']} normal)",
        "-" * 68,
        "Stage 1 Performance Metrics (No ML involved):",
        f"  Precision:         {results['precision'] * 100.0:6.2f}%",
        f"  Recall (TPR):      {results['recall'] * 100.0:6.2f}%",
        f"  False Pos. Rate:   {results['fpr'] * 100.0:6.2f}%  ({cm['fp']} false flags / {cm['fp'] + cm['tn']} normal)",
        f"  F1 Score:          {results['f1_score']:6.4f}",
        f"  Filtering Rate:    {results['filtering_rate'] * 100.0:6.2f}%  (share of frames marked CLEAN)",
        "-" * 68,
        "Confusion Matrix:",
        f"  True Positives  (TP): {cm['tp']:6d}    False Positives (FP): {cm['fp']:6d}",
        f"  False Negatives (FN): {cm['fn']:6d}    True Negatives  (TN): {cm['tn']:6d}",
        "-" * 68,
        "Stage 1 Latency (Demo Slide Metrics):",
        f"  Median Latency:    {lat['median']:8.4f} ms / frame",
        f"  Mean Latency:      {lat['mean']:8.4f} ms / frame",
        f"  95th Percentile:   {lat['p95']:8.4f} ms / frame",
        f"  99th Percentile:   {lat['p99']:8.4f} ms / frame",
        "-" * 68,
        "Rule Trigger Breakdown:",
    ]
    for r_id in ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]:
        hits = results["rule_hits"].get(r_id, 0)
        lines.append(f"  {r_id:2s} hits:            {hits:6d}")

    if results["per_attack_recall"]:
        lines.append("-" * 68)
        lines.append("Per-Attack-Type Recall:")
        for att, stats in results["per_attack_recall"].items():
            lines.append(
                f"  {att:16s}: {stats['recall'] * 100.0:6.2f}% ({stats['detected']}/{stats['total']})"
            )
    lines.append("=" * 68)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for Stage 1 evaluation."""
    parser = argparse.ArgumentParser(
        description="Measure Stage 1 RuleEngine standalone on validation split."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="Optional path to custom CAN traffic CSV to evaluate (overrides auto-detection).",
    )
    parser.add_argument(
        "--rules-yaml",
        type=Path,
        default=Path("config/rules.yaml"),
        help="Path to rules.yaml base schema (default: config/rules.yaml).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/stage1_only_metrics.json"),
        help="Output metrics JSON destination (default: reports/stage1_only_metrics.json).",
    )

    args = parser.parse_args(argv)

    print("Loading validation split...")
    train_df, val_df, is_fixture, source_desc = load_dataset_splits(
        data_override=args.data
    )
    normal_train_df, _ = filter_normal_frames(train_df)

    print(f"Data source: {source_desc}")
    print(f"Data type:   {'Synthetic Fixture' if is_fixture else 'Real Dataset'}")
    print(
        f"Loaded:      {len(train_df)} train frames ({len(normal_train_df)} normal), {len(val_df)} val frames."
    )

    print("\nRebuilding thresholds from TRAIN normal frames only...")
    engine, profiler, _ = rebuild_stage1_engine(
        train_df, rules_yaml_path=args.rules_yaml
    )
    print(
        f"Fitted BaselineProfiler with {len(profiler.id_whitelist)} authorized CAN IDs."
    )

    print("\nEvaluating RuleEngine over VALIDATION split frames...")
    results = evaluate_stage1_dataset(val_df, engine)

    meta = {
        "source_desc": source_desc,
        "is_fixture": is_fixture,
        "train_frames": len(train_df),
        "train_normal_frames": len(normal_train_df),
        "rules_yaml_path": str(args.rules_yaml),
    }

    report_str = format_table(results, meta)
    print("\n" + report_str)

    # Save to reports/stage1_only_metrics.json
    out_payload = {
        "metadata": meta,
        "metrics": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_payload, f, indent=2)

    print(f"\nSaved metrics to: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
