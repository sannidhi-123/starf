#!/usr/bin/env python3
"""Derive Stage 1 baseline distributions and thresholds for STARK Detection Pipeline.

Reads normal baseline CAN-Bus traffic (benign training split or fixture), runs
BaselineProfiler to extract per-CAN-ID statistics, computes global bus message
rate limits, and populates config/rules.yaml while preserving the skeleton schema
and documentation comments.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Any, List, Optional

import numpy as np
import pandas as pd
import yaml

from stark.baseline.profiler import BaselineProfiler


def calculate_50ms_message_count_p999(
    df: pd.DataFrame,
    time_col: str,
) -> float:
    """Compute the 99.9th percentile of total bus message count in trailing 50ms windows.

    Args:
        df: DataFrame containing normal traffic frames.
        time_col: Name of the timestamp column in seconds.

    Returns:
        float: 99.9th percentile of frame count in a 50ms window.
    """
    timestamps = df[time_col].sort_values().values
    if len(timestamps) == 0:
        return 0.0

    # Vectorized sliding 50ms window count using binary search
    left_indices = np.searchsorted(timestamps, timestamps - 0.050, side="left")
    counts = np.arange(len(timestamps)) - left_indices + 1
    return float(np.percentile(counts, 99.9))


def format_scalar(val: Any) -> str:
    """Format scalar value for YAML output."""
    if isinstance(val, (bool, np.bool_)):
        return "true" if val else "false"
    if isinstance(val, (int, np.integer)):
        return str(int(val))
    if isinstance(val, (float, np.floating)):
        if float(val).is_integer():
            return f"{float(val):.1f}"
        # Up to 6 significant digits for microsecond-level timing
        return f"{float(val):.6f}".rstrip("0").rstrip(".")
    return str(val)


def update_rules_yaml(
    skeleton_path: Path,
    out_path: Path,
    profiler: BaselineProfiler,
    r3_global_rate: float,
    r2_factor: float = 0.5,
    r7_factor: float = 5.0,
) -> None:
    """Populate rules.yaml with derived thresholds while preserving comments.

    Args:
        skeleton_path: Path to read skeleton comments and keys from.
        out_path: Destination path for populated YAML file.
        profiler: Fitted BaselineProfiler instance.
        r3_global_rate: 99.9th percentile of 50ms window message count.
        r2_factor: Multiplier for impossible inter-arrival floor (default 0.5).
        r7_factor: Multiplier for silence timeout watchdog (default 5.0).
    """
    # 1. Read existing template or create default
    if skeleton_path.exists():
        with open(skeleton_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Verify valid YAML structure
        skeleton_data = yaml.safe_load(content)
        if not isinstance(skeleton_data, dict):
            raise ValueError(f"Invalid YAML structure in {skeleton_path}")
    else:
        # Fallback to safe_dump if skeleton file doesn't exist
        content = ""
        skeleton_data = {}

    # 2. Update global values in text
    if content:
        # Replace global threshold values
        content = re.sub(
            r"(r2_factor:\s*)[\d\.]+",
            rf"\g<1>{format_scalar(r2_factor)}",
            content,
        )
        content = re.sub(
            r"(r3_global_rate:\s*)[\d\.]+",
            rf"\g<1>{format_scalar(r3_global_rate)}",
            content,
        )
        content = re.sub(
            r"(r7_factor:\s*)[\d\.]+",
            rf"\g<1>{format_scalar(r7_factor)}",
            content,
        )

        # Helper to replace mapping blocks under per_id_baselines
        def replace_mapping_block(
            text: str,
            section_key: str,
            items: List[str],
        ) -> str:
            # Matches '  section_key:\n' followed by indented items and comments
            pattern = rf"(  {section_key}:\n)(?:    [^\n]+\n)+"
            replacement = r"\g<1>" + "".join(f"    {line}\n" for line in items)
            if re.search(pattern, text):
                return re.sub(pattern, replacement, text)
            return text

        ids = sorted(profiler.id_whitelist)

        content = replace_mapping_block(
            content,
            "id_whitelist",
            [f"- 0x{can_id:04X}" for can_id in ids],
        )
        content = replace_mapping_block(
            content,
            "is_periodic",
            [
                f"0x{can_id:04X}: {format_scalar(profiler.is_periodic[can_id])}"
                for can_id in ids
            ],
        )
        content = replace_mapping_block(
            content,
            "modal_dlc",
            [
                f"0x{can_id:04X}: {format_scalar(profiler.modal_dlc[can_id])}"
                for can_id in ids
            ],
        )
        content = replace_mapping_block(
            content,
            "p01_dt",
            [
                f"0x{can_id:04X}: {format_scalar(profiler.p01_dt[can_id])}"
                for can_id in ids
            ],
        )
        content = replace_mapping_block(
            content,
            "p99_dt",
            [
                f"0x{can_id:04X}: {format_scalar(profiler.p99_dt[can_id])}"
                for can_id in ids
            ],
        )
        content = replace_mapping_block(
            content,
            "p995_rep",
            [
                f"0x{can_id:04X}: {format_scalar(profiler.p995_rep[can_id])}"
                for can_id in ids
            ],
        )
        content = replace_mapping_block(
            content,
            "p99_hamming",
            [
                f"0x{can_id:04X}: {format_scalar(profiler.p99_hamming[can_id])}"
                for can_id in ids
            ],
        )

        # Validate that the populated text is completely valid YAML
        validated_data = yaml.safe_load(content)
        assert "per_id_baselines" in validated_data
        assert "global_tuned_thresholds" in validated_data

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)

    else:
        # If no skeleton was present, construct dictionary and safe_dump
        ids = sorted(profiler.id_whitelist)
        output_dict = {
            "version": "1.0",
            "vehicle_profile": "generic_can_profile",
            "global_tuned_thresholds": {
                "r2_factor": r2_factor,
                "r3_global_rate": r3_global_rate,
                "r7_factor": r7_factor,
                "physical_min_dt": 0.00020,
                "modal_dlc_default": 8,
                "default_max_repetition": 5,
                "default_max_hamming": 48,
            },
            "per_id_baselines": {
                "id_whitelist": [int(i) for i in ids],
                "is_periodic": {
                    int(k): bool(v) for k, v in profiler.is_periodic.items()
                },
                "modal_dlc": {int(k): int(v) for k, v in profiler.modal_dlc.items()},
                "p01_dt": {int(k): float(v) for k, v in profiler.p01_dt.items()},
                "p99_dt": {int(k): float(v) for k, v in profiler.p99_dt.items()},
                "p995_rep": {int(k): float(v) for k, v in profiler.p995_rep.items()},
                "p99_hamming": {
                    int(k): float(v) for k, v in profiler.p99_hamming.items()
                },
            },
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(output_dict, f, sort_keys=False)


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for deriving Stage 1 baseline thresholds."""
    parser = argparse.ArgumentParser(
        description="Derive Stage 1 thresholds from normal traffic into rules.yaml."
    )
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="Path to normal CAN traffic CSV (training split or fixture).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("config/rules.yaml"),
        help="Path to output rules.yaml file (default: config/rules.yaml).",
    )

    parsed = parser.parse_args(args)
    data_path: Path = parsed.data
    out_path: Path = parsed.out

    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}", file=sys.stderr)
        return 1

    print(f"Loading CAN traffic data from: {data_path}")
    df = pd.read_csv(data_path, dtype={"CAN ID": str, "can_id": str})

    # Filter to NORMAL-only frames
    flag_col = None
    for cand in ["Flag", "flag", "label", "status"]:
        if cand in df.columns:
            flag_col = cand
            break

    if flag_col is not None:
        flags = set(df[flag_col].dropna().unique())
        if "R" in flags:
            normal_df = df[df[flag_col] == "R"].copy()
        elif "normal" in flags:
            normal_df = df[df[flag_col] == "normal"].copy()
        elif 0 in flags:
            normal_df = df[df[flag_col] == 0].copy()
        else:
            normal_df = df.copy()
    else:
        normal_df = df.copy()

    total_frames = len(df)
    normal_frames = len(normal_df)
    print(
        f"Loaded {total_frames} total frames; retained {normal_frames} NORMAL frames."
    )

    if normal_df.empty:
        print("Error: No normal frames found after filtering.", file=sys.stderr)
        return 1

    # Fit BaselineProfiler
    print("Fitting BaselineProfiler on normal traffic...")
    profiler = BaselineProfiler()
    profiler.fit(normal_df)

    # Compute global values
    time_col = "Timestamp" if "Timestamp" in normal_df.columns else "timestamp"
    r3_global_rate = calculate_50ms_message_count_p999(normal_df, time_col=time_col)

    # Default factor parameters (tuned on Day 12 validation sprint)
    r2_factor = 0.5
    r7_factor = 5.0

    print(f"Derived r3_global_rate (p999 of 50ms message count): {r3_global_rate}")
    print(f"Using default r2_factor: {r2_factor}, r7_factor: {r7_factor}")
    print(f"Identified {len(profiler.id_whitelist)} authorized CAN IDs:")
    for can_id in profiler.id_whitelist:
        print(
            f"  - ID 0x{can_id:04X}: "
            f"p01_dt={profiler.p01_dt[can_id]:.6f}s, "
            f"p99_dt={profiler.p99_dt[can_id]:.6f}s, "
            f"dlc={profiler.modal_dlc[can_id]}, "
            f"periodic={profiler.is_periodic[can_id]}"
        )

    # Write populated rules.yaml
    print(f"Writing populated configuration to: {out_path}")
    update_rules_yaml(
        skeleton_path=out_path,
        out_path=out_path,
        profiler=profiler,
        r3_global_rate=r3_global_rate,
        r2_factor=r2_factor,
        r7_factor=r7_factor,
    )

    print(
        "\n[NOTE] Fixture-derived values are placeholders until the real training split lands."
    )
    print("Successfully populated Stage 1 thresholds into rules.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
