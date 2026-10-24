"""Load, clean, and featurize Car-Hacking CAN frames."""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

BYTE_COLUMNS = [f"d{index}" for index in range(8)]
NUMERIC_FEATURES = [
    "can_id",
    "dlc",
    "dt_id",
    "dt_global",
    "freq_id",
    "freq_global",
    "payload_mean",
    "payload_std",
    "byte_entropy",
    "bit_flip_distance",
    "changed_bytes",
    *BYTE_COLUMNS,
]
FRAME_COLUMNS = ["timestamp", "can_id", "dlc", *BYTE_COLUMNS, "flag", "attack_type", "y"]
_BYTE_POPCOUNT = np.array([value.bit_count() for value in range(256)], dtype=np.uint8)
_ATTACK_NAMES = {
    "normal": "normal",
    "dos": "dos",
    "fuzzy": "fuzzy",
    "gear": "gear_spoofing",
    "gear_spoofing": "gear_spoofing",
    "rpm": "rpm_spoofing",
    "rpm_spoofing": "rpm_spoofing",
}


@dataclass
class FeatureScaler:
    """Small joblib-serializable standard scaler for numeric feature arrays."""

    mean_: np.ndarray
    scale_: np.ndarray

    @classmethod
    def fit(cls, values: np.ndarray) -> "FeatureScaler":
        if values.ndim != 2 or values.shape[0] == 0:
            raise ValueError("Scaler requires a non-empty 2D training array")
        mean = values.mean(axis=0, dtype=np.float64)
        scale = values.std(axis=0, dtype=np.float64)
        scale[scale == 0] = 1.0
        return cls(mean_=mean, scale_=scale)

    def transform(self, values: np.ndarray) -> np.ndarray:
        return ((values.astype(np.float64, copy=False) - self.mean_) / self.scale_).astype(
            np.float32
        )


def _attack_type_from_filename(path: Path) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
    for token, attack_type in _ATTACK_NAMES.items():
        if normalized == token or token in normalized.split("_"):
            return attack_type
    return normalized or "unknown"


def _parse_hex_byte(value: str) -> int:
    token = value.strip()
    if not re.fullmatch(r"(?:0x)?[0-9a-fA-F]{1,2}", token):
        raise ValueError("invalid payload byte")
    return int(token, 16)


def _payload_tokens(fields: list[str], dlc: int) -> list[str]:
    if len(fields) == 4:
        return []
    payload_fields = fields[3:-1]
    if len(payload_fields) != 1:
        return payload_fields

    payload = payload_fields[0].strip()
    if not payload:
        return []
    if re.search(r"\s", payload):
        return payload.split()
    contiguous = payload[2:] if payload.lower().startswith("0x") else payload
    if len(contiguous) == dlc * 2 and re.fullmatch(r"[0-9a-fA-F]*", contiguous):
        return [contiguous[index : index + 2] for index in range(0, len(contiguous), 2)]
    return [payload]


def _parse_line(line: str, path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        fields = [field.strip() for field in next(csv.reader([line], skipinitialspace=True))]
    except (csv.Error, StopIteration):
        return None, "unparseable"
    if len(fields) < 4:
        return None, "unparseable"

    try:
        dlc = int(fields[2], 10)
    except ValueError:
        return None, "corrupted"
    if dlc < 0 or dlc > 8:
        return None, "dlc_out_of_range"

    try:
        timestamp = float(fields[0])
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("invalid timestamp")
        can_id = int(fields[1], 16)
        flag = fields[-1].upper()
        if flag not in {"R", "T"}:
            raise ValueError("invalid frame flag")
        tokens = _payload_tokens(fields, dlc)
        if len(tokens) != dlc:
            return None, "dlc_mismatch"
        payload = [_parse_hex_byte(token) for token in tokens]
    except (ValueError, OverflowError):
        return None, "corrupted"

    bytes_padded = payload + [0] * (8 - dlc)
    return {
        "timestamp": timestamp,
        "can_id": can_id,
        "dlc": dlc,
        **dict(zip(BYTE_COLUMNS, bytes_padded)),
        "flag": flag,
        "attack_type": _attack_type_from_filename(path),
        "y": int(flag == "T"),
    }, None


def _input_files(input_path: str | Path | None) -> list[Path]:
    if input_path is None:
        root = Path(__file__).resolve().parents[4] / "data"
    else:
        root = Path(input_path)
    if root.is_file():
        return [root]
    if root.is_dir():
        return sorted(path for path in root.rglob("*") if path.is_file() and path.name != ".gitkeep")
    raise FileNotFoundError(f"Dataset path does not exist: {root}")


def load_datasets(
    input_path: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load one file or all files under data/, returning cleaned frames and counts."""
    parsed_rows: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "rows_in": 0,
        "rows_out": 0,
        "removed_per_reason": {
            "unparseable": 0,
            "dlc_out_of_range": 0,
            "dlc_mismatch": 0,
            "corrupted": 0,
        },
    }

    for path in _input_files(input_path):
        with path.open("r", encoding="utf-8-sig", errors="replace") as source:
            for line in source:
                report["rows_in"] += 1
                row, reason = _parse_line(line, path)
                if reason is not None:
                    report["removed_per_reason"][reason] += 1
                else:
                    parsed_rows.append(row)

    frames = pd.DataFrame(parsed_rows, columns=FRAME_COLUMNS)
    if not frames.empty:
        frames = frames.sort_values("timestamp", kind="mergesort", ignore_index=True)
        frames["can_id"] = frames["can_id"].astype(np.int64)
        frames["dlc"] = frames["dlc"].astype(np.uint8)
        frames["y"] = frames["y"].astype(np.uint8)
        frames[BYTE_COLUMNS] = frames[BYTE_COLUMNS].astype(np.uint8)
    report["rows_out"] = len(frames)
    return frames, report


def _sliding_frequency(timestamps: np.ndarray, window_seconds: float = 1.0) -> np.ndarray:
    left_edges = np.searchsorted(timestamps, timestamps - window_seconds, side="left")
    right_edges = np.arange(1, len(timestamps) + 1)
    return (right_edges - left_edges).astype(np.int32)


def _byte_entropy(payload: np.ndarray, dlc: np.ndarray, chunk_size: int = 100_000) -> np.ndarray:
    entropy = np.zeros(len(payload), dtype=np.float32)
    columns = np.arange(8)
    for start in range(0, len(payload), chunk_size):
        stop = min(start + chunk_size, len(payload))
        chunk = payload[start:stop]
        valid = columns[None, :] < dlc[start:stop, None]
        equal = chunk[:, :, None] == chunk[:, None, :]
        counts = np.sum(equal & valid[:, None, :], axis=2)
        probabilities = counts / np.maximum(dlc[start:stop, None], 1)
        terms = np.zeros_like(probabilities, dtype=np.float32)
        np.log2(probabilities, out=terms, where=valid & (probabilities > 0))
        entropy[start:stop] = -np.sum(terms, axis=1) / np.maximum(dlc[start:stop], 1)
    return entropy


def extract_features(frames: pd.DataFrame) -> pd.DataFrame:
    """Add temporal, payload-statistical, and sequential payload features."""
    result = frames.copy()
    if result.empty:
        for feature in NUMERIC_FEATURES:
            if feature not in result:
                result[feature] = pd.Series(dtype=np.float32)
        return result

    timestamps = result["timestamp"].to_numpy(dtype=np.float64)
    ids = result["can_id"].to_numpy()
    payload = result[BYTE_COLUMNS].to_numpy(dtype=np.uint8, copy=False)
    dlc = result["dlc"].to_numpy(dtype=np.uint8)

    result["dt_global"] = np.r_[0.0, np.diff(timestamps)]
    result["freq_global"] = _sliding_frequency(timestamps)
    grouped = result.groupby("can_id", sort=False, observed=True)
    result["dt_id"] = grouped["timestamp"].diff().fillna(0.0).to_numpy()
    frequencies = np.empty(len(result), dtype=np.int32)
    for indices in grouped.indices.values():
        frequencies[indices] = _sliding_frequency(timestamps[indices])
    result["freq_id"] = frequencies

    valid = np.arange(8)[None, :] < dlc[:, None]
    payload_values = payload.astype(np.float32)
    payload_sums = np.sum(payload_values * valid, axis=1)
    denominators = np.maximum(dlc, 1)
    means = payload_sums / denominators
    variances = np.sum(((payload_values - means[:, None]) ** 2) * valid, axis=1) / denominators
    result["payload_mean"] = np.where(dlc > 0, means, 0.0)
    result["payload_std"] = np.sqrt(np.maximum(variances, 0.0))
    result["byte_entropy"] = _byte_entropy(payload, dlc)

    previous_payload = grouped[BYTE_COLUMNS].shift().fillna(0).to_numpy(dtype=np.uint8)
    payload_xor = np.bitwise_xor(payload, previous_payload)
    result["bit_flip_distance"] = _BYTE_POPCOUNT[payload_xor].sum(axis=1, dtype=np.uint16)
    result["changed_bytes"] = np.count_nonzero(payload_xor, axis=1).astype(np.uint8)
    result[BYTE_COLUMNS] = payload
    return result


def split_and_scale_features(
    frames: pd.DataFrame, scaler_path: str | Path | None = None
) -> dict[str, Any]:
    """Chronologically split features and normalize using training statistics only."""
    row_count = len(frames)
    train_end = int(row_count * 0.70)
    validation_end = int(row_count * 0.85)
    if train_end == 0:
        raise ValueError("At least two frames are required to create a training split")

    values = frames[NUMERIC_FEATURES].to_numpy(dtype=np.float32, copy=False)
    labels = frames["y"].to_numpy(dtype=np.uint8, copy=False)
    scaler = FeatureScaler.fit(values[:train_end])
    if scaler_path is not None:
        path = Path(scaler_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(scaler, path)

    return {
        "X_train": scaler.transform(values[:train_end]),
        "X_val": scaler.transform(values[train_end:validation_end]),
        "X_test": scaler.transform(values[validation_end:]),
        "y_train": labels[:train_end],
        "y_val": labels[train_end:validation_end],
        "y_test": labels[validation_end:],
        "scaler": scaler,
        "train_end": train_end,
        "validation_end": validation_end,
    }


def make_sequences(
    X: np.ndarray, y: np.ndarray, seq_len: int, stride: int
) -> tuple[np.ndarray, np.ndarray]:
    """Return strided windows; a window is positive when any frame is an attack."""
    X = np.asarray(X)
    y = np.asarray(y)
    if X.ndim != 2 or y.ndim != 1 or len(X) != len(y):
        raise ValueError("X must be 2D and y must be 1D with matching row counts")
    if seq_len <= 0 or stride <= 0:
        raise ValueError("seq_len and stride must be positive")
    if len(X) < seq_len:
        return np.empty((0, seq_len, X.shape[1]), dtype=X.dtype), np.empty(0, dtype=np.uint8)

    windows = sliding_window_view(X, seq_len, axis=0).transpose(0, 2, 1)[::stride]
    labels = sliding_window_view(y, seq_len)[::stride].any(axis=1).astype(np.uint8)
    return windows, labels


def _main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess a Car-Hacking CAN dataset file")
    parser.add_argument("input_path", help="Input dataset file or directory")
    parser.add_argument("output_parquet", help="Destination feature dataset in Parquet format")
    args = parser.parse_args()

    frames, report = load_datasets(args.input_path)
    features = extract_features(frames)
    output_path = Path(args.output_parquet)
    scaler_path = output_path.with_suffix(".scaler.joblib")
    split = split_and_scale_features(features, scaler_path)
    all_values = features[NUMERIC_FEATURES].to_numpy(dtype=np.float32, copy=False)
    normalized = split["scaler"].transform(all_values)
    features.loc[:, NUMERIC_FEATURES] = normalized
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output_path, index=False)
    print({**report, "scaler_path": str(scaler_path), "output_path": str(output_path)})


if __name__ == "__main__":
    _main()