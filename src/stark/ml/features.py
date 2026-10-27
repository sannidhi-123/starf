"""Shared feature schema and CSV normalization for model training/inference."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

FEATURE_NAMES: Tuple[str, ...] = (
    "can_id",
    "dlc",
    "dt_same_id",
    "msg_rate_50ms",
    "payload_hamming_distance",
    "byte_entropy",
    "can_id_count_50ms",
    "payload_repeat_streak",
)
LABEL_ALIASES = {
    "r": "normal",
    "regular": "normal",
    "normal": "normal",
    "0": "normal",
    "t": "attack",
    "attack": "attack",
    "1": "attack",
    "dos": "dos",
    "fuzzy": "fuzzy",
    "spoofing-gear": "spoofing",
    "spoofing-rpm": "spoofing",
    "spoofing": "spoofing",
    "impersonation": "impersonation",
}


def normalize_label(value: Any) -> str:
    """Map documented Car-Hacking and common OTIDS labels to stable names."""
    text = str(value).strip().lower()
    return LABEL_ALIASES.get(text, text if text else "unknown")


def _column(columns: Iterable[Any], names: Iterable[str]) -> Any:
    lookup = {str(c).strip().lower(): c for c in columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def normalize_dataset(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize supported CSV column aliases and preserve original columns.

    Malformed rows are removed with an actionable error if no usable rows remain.
    This adapter intentionally does not guess label semantics for unknown values.
    """
    if frame.empty:
        raise ValueError("Dataset is empty")
    ts_col = _column(frame.columns, ("timestamp", "time", "ts"))
    id_col = _column(frame.columns, ("can_id", "can id", "id", "arbitration_id"))
    dlc_col = _column(frame.columns, ("dlc", "length", "data_length"))
    label_col = _column(
        frame.columns, ("attack_type", "label", "flag", "class", "status")
    )
    if ts_col is None or id_col is None:
        raise ValueError("Dataset requires timestamp/time and CAN ID columns")

    result = frame.copy()
    result["timestamp"] = pd.to_numeric(frame[ts_col], errors="coerce")

    def parse_id(value: Any) -> float:
        try:
            raw = str(value).strip()
            # The Car-Hacking "CAN ID" column is hexadecimal without a 0x
            # prefix; normalized can_id/arbitration_id columns use decimal.
            is_car_hacking = str(id_col).strip().lower() == "can id"
            return (
                int(raw, 16)
                if raw.lower().startswith("0x") or is_car_hacking
                else int(raw, 16 if any(c in "abcdefABCDEF" for c in raw) else 10)
            )
        except (TypeError, ValueError):
            return float("nan")

    result["can_id"] = frame[id_col].map(parse_id)
    result["dlc"] = (
        pd.to_numeric(frame[dlc_col], errors="coerce") if dlc_col is not None else 0
    )
    result = result.dropna(subset=["timestamp", "can_id", "dlc"])
    result = result[
        (result["can_id"].between(0, 0x1FFFFFFF)) & (result["dlc"].between(0, 8))
    ]
    payload_col = _column(frame.columns, ("payload", "data", "bytes"))
    data_cols = [f"DATA[{i}]" for i in range(8) if f"DATA[{i}]" in frame.columns]

    def payload_valid(index: Any) -> bool:
        try:
            if data_cols:
                values = [frame.at[index, col] for col in data_cols]
                bytes_seen = [
                    str(value).strip()
                    for value in values
                    if pd.notna(value) and str(value).strip()
                ]
                decoded = [int(value, 16) for value in bytes_seen]
            elif payload_col is not None and pd.notna(frame.at[index, payload_col]):
                value = (
                    str(frame.at[index, payload_col]).replace("0x", "").replace(" ", "")
                )
                decoded = list(bytes.fromhex(value)) if value else []
            else:
                return True
            return all(0 <= byte <= 255 for byte in decoded) and len(decoded) == int(
                result.at[index, "dlc"]
            )
        except (ValueError, TypeError, KeyError):
            return False

    result = result.loc[[idx for idx in result.index if payload_valid(idx)]]
    if result.empty:
        raise ValueError(
            "No valid rows remain after timestamp, CAN ID, and DLC validation"
        )
    if label_col is not None:
        result["label"] = frame.loc[result.index, label_col].map(normalize_label)
    result = result.sort_values("timestamp", kind="stable").reset_index(drop=True)
    return result


def frame_to_vector(frame: Dict[str, Any]) -> List[float]:
    """Build a fixed-order numeric model vector from causal streaming features."""
    defaults = {name: 0.0 for name in FEATURE_NAMES}
    defaults.update(frame)
    if "payload_repeat_streak" not in frame:
        # The R5 rule engine's historic key is an identical-payload streak;
        # keep that meaning distinct from team feature contracts where
        # id_repetition_count means repeated CAN IDs over a frame window.
        defaults["payload_repeat_streak"] = frame.get("id_repetition_count") or 0.0
    if (
        "payload_hamming_distance" not in frame
        or defaults.get("payload_hamming_distance") is None
    ):
        defaults["payload_hamming_distance"] = frame.get("hamming_prev_same_id") or 0.0
    values: List[float] = []
    for name in FEATURE_NAMES:
        try:
            value = float(defaults.get(name) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if not pd.notna(value):
            value = 0.0
        values.append(value)
    return values
