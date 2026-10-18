"""Baseline profiler for CAN-Bus anomaly detection in STARK (Stage 1).

Extracts empirical per-CAN-ID baseline statistics from benign baseline traffic:
- id_whitelist: Set/list of all authorized CAN IDs seen in normal traffic
- is_periodic: Periodicity classification flag (True for cyclic ECUs)
- modal_dlc: Mode of Data Length Code (DLC) per CAN ID
- p01_dt: 1st percentile of inter-arrival time (dt) in seconds per CAN ID
- p99_dt: 99th percentile of inter-arrival time (dt) in seconds per CAN ID
- p995_rep: 99.5th percentile of consecutive identical payload repetition counts
- p99_hamming: 99th percentile of bitwise Hamming distance between consecutive frames of same ID

Conforms to Stage 1 Rule Engine specifications (docs/rule_spec.md, config/rules.yaml).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd
import yaml

# Try importing Person 1's FeatureState if it exists in the codebase
try:
    from stark.features.state import FeatureState  # type: ignore
except ImportError:
    # TODO: Swap in Person 1's FeatureState output once stark.features.state lands on Day 7
    FeatureState = None


class ProfileDict(dict):
    """Dictionary subclass supporting transparent CAN ID lookups.

    Supports indexing via:
    - Decimal integer (e.g. 320 or 140)
    - Hexadecimal integer (e.g. 0x0140 == 320)
    - Hexadecimal string with or without '0x' prefix (e.g. '0x0140', '0140')
    """

    def _resolve_key(self, key: Any) -> Any:
        if super().__contains__(key):
            return key

        # If key is string
        if isinstance(key, str):
            k_clean = key.strip()
            # If key starts with 0x/0X
            if k_clean.lower().startswith("0x"):
                try:
                    int_val = int(k_clean, 16)
                    if super().__contains__(int_val):
                        return int_val
                    # Could be stored as decimal representation of hex digits (e.g. 140 from '0140')
                    hex_str = f"{int_val:X}"
                    if hex_str.isdigit() and super().__contains__(int(hex_str)):
                        return int(hex_str)
                except ValueError:
                    pass
            # Try direct decimal parse
            try:
                dec_val = int(k_clean, 10)
                if super().__contains__(dec_val):
                    return dec_val
            except ValueError:
                pass
            # Try raw hex parse without 0x
            try:
                hex_val = int(k_clean, 16)
                if super().__contains__(hex_val):
                    return hex_val
                hex_str = f"{hex_val:X}"
                if hex_str.isdigit() and super().__contains__(int(hex_str)):
                    return int(hex_str)
            except ValueError:
                pass

        # If key is integer
        elif isinstance(key, (int, np.integer)):
            key_int = int(key)
            # 1. key_int might be 320 (0x140), stored is 140
            hex_str = f"{key_int:X}"
            if hex_str.isdigit() and super().__contains__(int(hex_str)):
                return int(hex_str)
            # 2. key_int might be 140, stored is 320 (0x140)
            try:
                hex_val = int(str(key_int), 16)
                if super().__contains__(hex_val):
                    return hex_val
            except ValueError:
                pass
            # 3. Check string forms in case keys were loaded as strings
            for str_form in [str(key_int), f"0x{key_int:X}", f"0x{key_int:04X}"]:
                if super().__contains__(str_form):
                    return str_form

        return key

    def __getitem__(self, key: Any) -> Any:
        resolved = self._resolve_key(key)
        return super().__getitem__(resolved)

    def __contains__(self, key: Any) -> bool:
        resolved = self._resolve_key(key)
        return super().__contains__(resolved)

    def get(self, key: Any, default: Any = None) -> Any:
        resolved = self._resolve_key(key)
        return super().get(resolved, default)


class BaselineProfiler:
    """Computes empirical baseline distributions per CAN ID from benign traffic.

    Attributes:
        id_whitelist (List[int]): Sorted list of unique CAN IDs seen in normal traffic.
        p01_dt (ProfileDict[int, float]): 1st percentile of inter-arrival time in seconds.
        p99_dt (ProfileDict[int, float]): 99th percentile of inter-arrival time in seconds.
        p995_rep (ProfileDict[int, float]): 99.5th percentile of consecutive identical payload counts.
        p99_hamming (ProfileDict[int, float]): 99th percentile of bitwise Hamming distance between
            consecutive payloads of the same ID.
        modal_dlc (ProfileDict[int, int]): Mode of Data Length Code (DLC) per CAN ID.
        is_periodic (ProfileDict[int, bool]): Periodicity flag per CAN ID.
    """

    def __init__(
        self,
        cv_threshold: float = 0.30,
        min_samples_for_periodicity: int = 5,
    ) -> None:
        """Initialize empty BaselineProfiler.

        Args:
            cv_threshold: Coefficient of variation (sigma / mu) threshold below which
                a CAN ID's inter-arrival distribution is classified as periodic (cyclic).
            min_samples_for_periodicity: Minimum number of delta_t samples required
                to establish cyclic periodicity.
        """
        self.cv_threshold = cv_threshold
        self.min_samples_for_periodicity = min_samples_for_periodicity

        self.id_whitelist: List[int] = []
        self.p01_dt: ProfileDict = ProfileDict()
        self.p99_dt: ProfileDict = ProfileDict()
        self.p995_rep: ProfileDict = ProfileDict()
        self.p99_hamming: ProfileDict = ProfileDict()
        self.modal_dlc: ProfileDict = ProfileDict()
        self.is_periodic: ProfileDict = ProfileDict()

    def _resolve_column(
        self,
        df: pd.DataFrame,
        candidates: List[str],
        required: bool = True,
    ) -> Optional[str]:
        """Find the matching column in DataFrame case-insensitively from candidate names."""
        df_cols_lower = {str(c).lower().strip(): c for c in df.columns}
        for cand in candidates:
            cand_lower = cand.lower().strip()
            if cand_lower in df_cols_lower:
                return df_cols_lower[cand_lower]
        if required:
            raise ValueError(
                f"Required column not found. Looked for candidates {candidates} in DataFrame columns: {list(df.columns)}"
            )
        return None

    def _extract_payload_bytes(
        self,
        row: pd.Series,
        payload_col: Optional[str],
        data_cols: List[str],
    ) -> bytes:
        """Extract bytes payload from row using either payload column or DATA[0..7] columns."""
        if payload_col is not None and pd.notna(row[payload_col]):
            val = row[payload_col]
            if isinstance(val, (bytes, bytearray)):
                return bytes(val)
            if isinstance(val, (list, tuple)):
                return bytes(val)
            if isinstance(val, str):
                cleaned = val.replace(" ", "").replace("0x", "").strip()
                if cleaned:
                    try:
                        return bytes.fromhex(cleaned)
                    except ValueError:
                        return cleaned.encode("utf-8")
                return b""

        if data_cols:
            byte_vals: List[int] = []
            for col in data_cols:
                v = row[col]
                if pd.isna(v):
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

        return b""

    def _calculate_bitwise_hamming(self, b1: bytes, b2: bytes) -> int:
        """Calculate bitwise Hamming distance between two byte sequences."""
        common_len = min(len(b1), len(b2))
        dist = sum(
            (x ^ y).bit_count() for x, y in zip(b1[:common_len], b2[:common_len])
        )
        # Penalty for length disparity (8 bits per missing byte)
        dist += abs(len(b1) - len(b2)) * 8
        return dist

    def fit(self, df: pd.DataFrame) -> BaselineProfiler:
        """Fit empirical baseline distributions on benign (NORMAL-only) frames.

        Args:
            df: DataFrame containing CAN traffic. If a Flag/label column is present
                (e.g. Car-Hacking dataset format), it automatically filters for normal
                frames ('R' or 'normal' or 0) if mixed data is provided.

        Returns:
            self: The fitted BaselineProfiler instance.
        """
        if df.empty:
            raise ValueError("Cannot fit BaselineProfiler on empty DataFrame")

        # 1. Filter to NORMAL-only frames if Flag/label column is present
        flag_col = self._resolve_column(
            df,
            ["flag", "label", "is_attack", "status", "attack"],
            required=False,
        )
        if flag_col is not None:
            unique_flags = set(df[flag_col].dropna().unique())
            # Car-Hacking dataset convention: 'R' is Regular/Normal, 'T' is Tampered/Attack
            if "R" in unique_flags and "T" in unique_flags:
                normal_df = df[df[flag_col] == "R"].copy()
            elif "normal" in unique_flags:
                normal_df = df[df[flag_col] == "normal"].copy()
            elif 0 in unique_flags and 1 in unique_flags:
                normal_df = df[df[flag_col] == 0].copy()
            else:
                normal_df = df.copy()
        else:
            normal_df = df.copy()

        if normal_df.empty:
            raise ValueError(
                "No NORMAL traffic rows found in input DataFrame after filtering."
            )

        # 2. Resolve columns
        id_col = self._resolve_column(
            normal_df,
            ["can_id", "can id", "canid", "id", "arbitration_id"],
            required=True,
        )
        assert id_col is not None

        time_col = self._resolve_column(
            normal_df,
            ["timestamp", "time", "ts", "epoch"],
            required=True,
        )
        assert time_col is not None

        dlc_col = self._resolve_column(
            normal_df,
            ["dlc", "data_length_code"],
            required=False,
        )

        # Check for pre-extracted features (e.g. from Person 1's FeatureState or upstream pipeline)
        # TODO: Swap in Person 1's FeatureState output once stark.features.state lands on Day 7
        dt_col = self._resolve_column(
            normal_df,
            ["dt_same_id", "delta_t", "dt", "time_delta"],
            required=False,
        )
        rep_col = self._resolve_column(
            normal_df,
            ["id_repetition_count", "repetition_count", "repetition", "rep_count"],
            required=False,
        )
        hamming_col = self._resolve_column(
            normal_df,
            ["hamming_prev_same_id", "hamming_distance", "hamming_prev", "hamming"],
            required=False,
        )

        # Payload columns for raw frames
        payload_col = self._resolve_column(
            normal_df,
            ["payload", "data", "bytes"],
            required=False,
        )
        data_cols: List[str] = []
        if payload_col is None:
            # Check for DATA[0]..DATA[7] or data[0]..data[7] or d0..d7
            for i in range(8):
                c = self._resolve_column(
                    normal_df,
                    [f"data[{i}]", f"data_{i}", f"d{i}"],
                    required=False,
                )
                if c is not None:
                    data_cols.append(c)

        # 3. Sort chronologically by timestamp
        normal_df = normal_df.sort_values(by=time_col)

        # Reset profiler state
        self.id_whitelist = []
        self.p01_dt = ProfileDict()
        self.p99_dt = ProfileDict()
        self.p995_rep = ProfileDict()
        self.p99_hamming = ProfileDict()
        self.modal_dlc = ProfileDict()
        self.is_periodic = ProfileDict()

        # 4. Group by CAN ID and compute statistics
        for raw_can_id, group in normal_df.groupby(id_col):
            # Parse CAN ID to canonical int if string
            if isinstance(raw_can_id, str):
                v_clean = raw_can_id.strip()
                try:
                    can_id = int(v_clean, 16)
                except ValueError:
                    can_id = int(v_clean)
            else:
                can_id = int(raw_can_id)

            self.id_whitelist.append(can_id)

            # --- A. Inter-arrival time (dt) ---
            if dt_col is not None and dt_col in group:
                dts = group[dt_col].dropna().values
                dts = dts[dts > 0]
            else:
                # Compute dt yourself from timestamp / can_id
                # TODO: Swap in Person 1's FeatureState output once stark.features.state lands on Day 7
                diffs = group[time_col].diff().dropna().values
                dts = diffs[diffs > 0]

            if len(dts) > 0:
                p01 = float(np.percentile(dts, 1.0))
                p99 = float(np.percentile(dts, 99.0))
                self.p01_dt[can_id] = p01
                self.p99_dt[can_id] = p99

                # --- B. Periodicity (is_periodic) ---
                if len(dts) >= self.min_samples_for_periodicity:
                    dt_mean = float(np.mean(dts))
                    dt_std = float(np.std(dts))
                    cv = (dt_std / dt_mean) if dt_mean > 0 else float("inf")
                    self.is_periodic[can_id] = bool(cv <= self.cv_threshold)
                else:
                    self.is_periodic[can_id] = False
            else:
                self.p01_dt[can_id] = 0.0
                self.p99_dt[can_id] = 0.0
                self.is_periodic[can_id] = False

            # --- C. Modal DLC (modal_dlc) ---
            if dlc_col is not None and dlc_col in group:
                dlc_series = group[dlc_col].dropna()
                if not dlc_series.empty:
                    mode_val = dlc_series.mode()
                    self.modal_dlc[can_id] = int(mode_val.iloc[0])
                else:
                    self.modal_dlc[can_id] = 8
            else:
                self.modal_dlc[can_id] = 8

            # --- D. Repetition burst (p995_rep) & Payload jump (p99_hamming) ---
            if rep_col is not None and rep_col in group:
                reps = group[rep_col].dropna().values
                if len(reps) > 0:
                    self.p995_rep[can_id] = float(np.percentile(reps, 99.5))
                else:
                    self.p995_rep[can_id] = 1.0
            else:
                # Compute consecutive identical payload counts
                payload_bytes_seq: List[bytes] = [
                    self._extract_payload_bytes(row, payload_col, data_cols)
                    for _, row in group.iterrows()
                ]

                rep_counts: List[int] = []
                curr_rep = 1
                prev_p: Optional[bytes] = None
                for p in payload_bytes_seq:
                    if prev_p is not None and p == prev_p:
                        curr_rep += 1
                    else:
                        curr_rep = 1
                        prev_p = p
                    rep_counts.append(curr_rep)

                if rep_counts:
                    self.p995_rep[can_id] = float(np.percentile(rep_counts, 99.5))
                else:
                    self.p995_rep[can_id] = 1.0

            if hamming_col is not None and hamming_col in group:
                hams = group[hamming_col].dropna().values
                if len(hams) > 0:
                    self.p99_hamming[can_id] = float(np.percentile(hams, 99.0))
                else:
                    self.p99_hamming[can_id] = 0.0
            else:
                # Compute consecutive bitwise Hamming distance
                if "payload_bytes_seq" not in locals():
                    payload_bytes_seq = [
                        self._extract_payload_bytes(row, payload_col, data_cols)
                        for _, row in group.iterrows()
                    ]

                hamming_dists: List[int] = []
                prev_bytes: Optional[bytes] = None
                for b in payload_bytes_seq:
                    if prev_bytes is not None:
                        hamming_dists.append(
                            self._calculate_bitwise_hamming(b, prev_bytes)
                        )
                    prev_bytes = b

                if hamming_dists:
                    self.p99_hamming[can_id] = float(np.percentile(hamming_dists, 99.0))
                else:
                    self.p99_hamming[can_id] = 0.0

        # Ensure id_whitelist is strictly sorted
        self.id_whitelist.sort()
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Export profiler baseline distributions to a dictionary."""
        return {
            "id_whitelist": list(self.id_whitelist),
            "is_periodic": dict(self.is_periodic),
            "modal_dlc": dict(self.modal_dlc),
            "p01_dt": dict(self.p01_dt),
            "p99_dt": dict(self.p99_dt),
            "p995_rep": dict(self.p995_rep),
            "p99_hamming": dict(self.p99_hamming),
        }

    def save(self, path: Union[str, Path]) -> None:
        """Save baseline profile to a YAML or JSON file.

        Args:
            path: Destination file path (.yaml, .yml, or .json).
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "per_id_baselines": {
                "id_whitelist": [int(i) for i in self.id_whitelist],
                "is_periodic": {int(k): bool(v) for k, v in self.is_periodic.items()},
                "modal_dlc": {int(k): int(v) for k, v in self.modal_dlc.items()},
                "p01_dt": {int(k): float(v) for k, v in self.p01_dt.items()},
                "p99_dt": {int(k): float(v) for k, v in self.p99_dt.items()},
                "p995_rep": {int(k): float(v) for k, v in self.p995_rep.items()},
                "p99_hamming": {int(k): float(v) for k, v in self.p99_hamming.items()},
            }
        }

        if p.suffix.lower() == ".json":
            # For JSON, keys must be strings
            json_compatible = {
                "per_id_baselines": {
                    k: (
                        {str(ik): iv for ik, iv in v.items()}
                        if isinstance(v, dict)
                        else v
                    )
                    for k, v in data["per_id_baselines"].items()
                }
            }
            with open(p, "w", encoding="utf-8") as f:
                json.dump(json_compatible, f, indent=2)
        else:
            with open(p, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False)

    @classmethod
    def load(cls, path: Union[str, Path]) -> BaselineProfiler:
        """Load baseline profile from a YAML or JSON file.

        Can be called as a class method (BaselineProfiler.load(path))
        or as an instance method (profiler.load(path)).

        Args:
            path: Source file path.

        Returns:
            BaselineProfiler instance populated with loaded statistics.
        """
        instance = cls() if isinstance(cls, type) else cls
        p = Path(path)

        if not p.exists():
            raise FileNotFoundError(f"Baseline profile file not found: {p}")

        if p.suffix.lower() == ".json":
            with open(p, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        else:
            with open(p, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)

        baselines = raw_data.get("per_id_baselines", raw_data)

        def _parse_dict(d: Dict[Any, Any], val_type: Any) -> ProfileDict:
            res = ProfileDict()
            for k, v in d.items():
                if isinstance(k, str) and k.lower().startswith("0x"):
                    k_int = int(k, 16)
                else:
                    k_int = int(k)
                res[k_int] = val_type(v)
            return res

        instance.id_whitelist = [
            int(x, 16) if isinstance(x, str) and x.lower().startswith("0x") else int(x)
            for x in baselines.get("id_whitelist", [])
        ]
        instance.is_periodic = _parse_dict(baselines.get("is_periodic", {}), bool)
        instance.modal_dlc = _parse_dict(baselines.get("modal_dlc", {}), int)
        instance.p01_dt = _parse_dict(baselines.get("p01_dt", {}), float)
        instance.p99_dt = _parse_dict(baselines.get("p99_dt", {}), float)
        instance.p995_rep = _parse_dict(baselines.get("p995_rep", {}), float)
        instance.p99_hamming = _parse_dict(baselines.get("p99_hamming", {}), float)

        return instance
