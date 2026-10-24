"""Causal streaming feature state for STARK CAN frames.

Enforces:
- Rule 5: Feature state resets at each capture boundary.
- Rule 6: Features are strictly causal: frame i uses only frames 0..i and the
          training-split baseline. id_repetition_count is backward-looking over
          the last 50 frames.
- Rule 7: Feature baseline (per-ID mean and std of dt, whitelist, frequency table)
          is computed strictly from training split normal frames only.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class FeatureBaseline:
    """Statistical baseline parameters computed strictly from training normal frames."""

    whitelist: set[int] = field(default_factory=set)
    id_ranks: dict[int, float] = field(default_factory=dict)
    dt_stats: dict[int, tuple[float, float]] = field(default_factory=dict)
    default_rank: float = 1.0

    @classmethod
    def fit(cls, train_df: pd.DataFrame) -> FeatureBaseline:
        """Fit baseline parameters from normal frames of the training DataFrame.

        Args:
            train_df: Training split canonical DataFrame.

        Returns:
            FeatureBaseline: Fitted baseline.
        """
        # Rule 7: Compute baseline from training split's normal frames only
        normal = train_df[train_df["label"] == 0]
        if normal.empty:
            return cls()

        counts = normal["can_id"].value_counts(sort=True)
        whitelist = set(counts.index.astype(int))

        id_ranks: dict[int, float] = {}
        for rank, cid in enumerate(counts.index, start=1):
            id_ranks[int(cid)] = float(rank)
        default_rank = float(len(whitelist) + 1)

        dt_stats: dict[int, tuple[float, float]] = {}
        for cid, group in normal.groupby("can_id", observed=True, sort=False):
            ts = group["timestamp"].to_numpy(dtype=np.float64)
            if len(ts) > 1:
                diffs = np.diff(ts)
                mean_dt = float(np.mean(diffs))
                std_dt = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0
                dt_stats[int(cid)] = (mean_dt, std_dt)
            else:
                dt_stats[int(cid)] = (0.0, 0.0)

        return cls(
            whitelist=whitelist,
            id_ranks=id_ranks,
            dt_stats=dt_stats,
            default_rank=default_rank,
        )


class FeatureState:
    """Stateful, causal streaming feature computer for offline and live detection."""

    def __init__(self, baseline: FeatureBaseline | None = None) -> None:
        """Initialize FeatureState with an optional training baseline.

        Args:
            baseline: Optional precomputed training normal baseline.
        """
        self.baseline = baseline if baseline is not None else FeatureBaseline()
        self.current_capture: str | None = None

        # Historical state buffers
        self.last_global_ts: float | None = None
        self.last_ts_by_id: dict[int, float] = {}
        self.dt_roll_by_id: dict[int, deque[float]] = {}
        self.history_50ms: deque[float] = deque()
        self.history_100ms: deque[tuple[float, int]] = deque()
        self.history_last_50_ids: deque[int] = deque(maxlen=50)
        self.last_payload_by_id: dict[int, tuple[int, tuple[int, ...]]] = {}

    def reset(self, capture_name: str | None = None) -> None:
        """Reset all state buffers at a capture boundary (Rule 5).

        Args:
            capture_name: New capture identifier.
        """
        self.current_capture = capture_name
        self.last_global_ts = None
        self.last_ts_by_id.clear()
        self.dt_roll_by_id.clear()
        self.history_50ms.clear()
        self.history_100ms.clear()
        self.history_last_50_ids.clear()
        self.last_payload_by_id.clear()

    def update(self, frame: dict[str, Any] | pd.Series) -> dict[str, float]:
        """Update causal state with a new frame and return its 20 model features.

        Args:
            frame: CAN frame mapping with timestamp, can_id, dlc, data_0..7, capture.

        Returns:
            dict[str, float]: Computed 20 model features.
        """
        capture = (
            str(frame.get("capture", ""))
            if isinstance(frame, dict)
            else str(frame["capture"])
        )
        if self.current_capture is None:
            self.current_capture = capture
        elif capture != self.current_capture:
            # Rule 5: Feature state resets at each capture boundary
            self.reset(capture)

        t = float(
            frame.get("timestamp", 0.0)
            if isinstance(frame, dict)
            else frame["timestamp"]
        )
        cid = int(
            frame.get("can_id", 0) if isinstance(frame, dict) else frame["can_id"]
        )
        dlc = int(frame.get("dlc", 0) if isinstance(frame, dict) else frame["dlc"])

        raw_payload = [
            int(
                frame.get(f"data_{k}", -1)
                if isinstance(frame, dict)
                else frame[f"data_{k}"]
            )
            for k in range(8)
        ]
        valid_payload = tuple(raw_payload[:dlc]) if dlc > 0 else ()

        # 1. can_id
        feat_can_id = float(cid)

        # 2. dlc
        feat_dlc = float(dlc)

        # 3. is_extended: 29-bit CAN ID (> 0x7FF = 2047)
        feat_is_extended = 1.0 if cid > 0x7FF else 0.0

        # 4. is_known_id: Whitelist presence
        feat_is_known_id = (
            1.0 if (self.baseline and cid in self.baseline.whitelist) else 0.0
        )

        # 5. id_rank: Normal frequency rank
        if self.baseline and cid in self.baseline.id_ranks:
            feat_id_rank = self.baseline.id_ranks[cid]
        else:
            feat_id_rank = self.baseline.default_rank if self.baseline else 1.0

        # 6. dt_global: Time since previous bus frame
        if self.last_global_ts is not None:
            feat_dt_global = max(t - self.last_global_ts, 0.0)
        else:
            feat_dt_global = 0.0

        # 7. dt_same_id: Time since previous frame with this ID
        if cid in self.last_ts_by_id:
            feat_dt_same_id = max(t - self.last_ts_by_id[cid], 0.0)
        else:
            feat_dt_same_id = 0.0

        # 8. dt_ratio & 9. dt_zscore
        mean_dt, std_dt = 0.0, 0.0
        if self.baseline and cid in self.baseline.dt_stats:
            mean_dt, std_dt = self.baseline.dt_stats[cid]

        if mean_dt > 0.0 and feat_dt_same_id > 0.0:
            feat_dt_ratio = feat_dt_same_id / mean_dt
        else:
            feat_dt_ratio = 1.0

        if std_dt > 0.0 and feat_dt_same_id > 0.0:
            feat_dt_zscore = (feat_dt_same_id - mean_dt) / std_dt
        else:
            feat_dt_zscore = 0.0

        # 10. dt_roll_mean_20 & 11. dt_roll_std_20
        roll_buf = self.dt_roll_by_id.setdefault(cid, deque(maxlen=20))
        if roll_buf:
            feat_dt_roll_mean_20 = float(sum(roll_buf) / len(roll_buf))
            if len(roll_buf) > 1:
                variance = sum((x - feat_dt_roll_mean_20) ** 2 for x in roll_buf) / (
                    len(roll_buf) - 1
                )
                feat_dt_roll_std_20 = float(math.sqrt(max(variance, 0.0)))
            else:
                feat_dt_roll_std_20 = 0.0
        else:
            feat_dt_roll_mean_20 = feat_dt_same_id
            feat_dt_roll_std_20 = 0.0

        # 12. msg_rate_50ms: Frames within backward 50 ms window [t - 0.050, t]
        cutoff_50ms = t - 0.050
        while self.history_50ms and self.history_50ms[0] < cutoff_50ms:
            self.history_50ms.popleft()
        self.history_50ms.append(t)
        feat_msg_rate_50ms = float(len(self.history_50ms))

        # 13. id_count_100ms & 15. unique_ids_100ms: Within backward 100 ms window
        cutoff_100ms = t - 0.100
        while self.history_100ms and self.history_100ms[0][0] < cutoff_100ms:
            self.history_100ms.popleft()
        self.history_100ms.append((t, cid))

        same_id_count = 0
        distinct_ids: set[int] = set()
        for ts_item, cid_item in self.history_100ms:
            distinct_ids.add(cid_item)
            if cid_item == cid:
                same_id_count += 1

        feat_id_count_100ms = float(same_id_count)
        feat_unique_ids_100ms = float(len(distinct_ids))

        # 14. id_repetition_count: Occurrences of cid in backward-looking window of last 50 frames
        self.history_last_50_ids.append(cid)
        feat_id_repetition_count = float(self.history_last_50_ids.count(cid))

        # 16. payload_sum: Sum of valid payload bytes
        feat_payload_sum = float(sum(valid_payload)) if valid_payload else 0.0

        # 17. payload_nonzero: Count of non-zero payload bytes
        feat_payload_nonzero = float(sum(1 for b in valid_payload if b != 0))

        # 18. payload_entropy: Shannon entropy base 2 over valid payload bytes
        if dlc <= 1:
            feat_payload_entropy = 0.0
        else:
            counts_dict: dict[int, int] = {}
            for b in valid_payload:
                counts_dict[b] = counts_dict.get(b, 0) + 1
            entropy = 0.0
            for count in counts_dict.values():
                p = count / dlc
                entropy -= p * math.log2(p)
            feat_payload_entropy = float(entropy)

        # 19. hamming_prev_same_id & 20. byte_change_ratio
        if cid in self.last_payload_by_id:
            prev_dlc, prev_bytes = self.last_payload_by_id[cid]
            common_len = min(dlc, prev_dlc)
            hamming_bits = 0
            changed_bytes = 0
            for k in range(common_len):
                xor_val = valid_payload[k] ^ prev_bytes[k]
                hamming_bits += xor_val.bit_count()
                if xor_val != 0:
                    changed_bytes += 1
            # Count differing byte positions outside common length
            changed_bytes += abs(dlc - prev_dlc)

            feat_hamming_prev_same_id = float(hamming_bits)
            feat_byte_change_ratio = float(changed_bytes / max(dlc, 1))
        else:
            feat_hamming_prev_same_id = 0.0
            feat_byte_change_ratio = 0.0

        # Update historical state
        self.last_global_ts = t
        self.last_ts_by_id[cid] = t
        if feat_dt_same_id > 0.0:
            roll_buf.append(feat_dt_same_id)
        self.last_payload_by_id[cid] = (dlc, valid_payload)

        out = {
            "can_id": feat_can_id,
            "dlc": feat_dlc,
            "is_extended": feat_is_extended,
            "is_known_id": feat_is_known_id,
            "id_rank": feat_id_rank,
            "dt_global": feat_dt_global,
            "dt_same_id": feat_dt_same_id,
            "dt_ratio": feat_dt_ratio,
            "dt_zscore": feat_dt_zscore,
            "dt_roll_mean_20": feat_dt_roll_mean_20,
            "dt_roll_std_20": feat_dt_roll_std_20,
            "msg_rate_50ms": feat_msg_rate_50ms,
            "id_count_100ms": feat_id_count_100ms,
            "id_repetition_count": feat_id_repetition_count,
            "unique_ids_100ms": feat_unique_ids_100ms,
            "payload_sum": feat_payload_sum,
            "payload_nonzero": feat_payload_nonzero,
            "payload_entropy": feat_payload_entropy,
            "hamming_prev_same_id": feat_hamming_prev_same_id,
            "byte_change_ratio": feat_byte_change_ratio,
        }
        return out
