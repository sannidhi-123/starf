"""Feature registry and single source of truth for STARK Stage 2 model features.

Defines the 20 model features used by the Stage 2 detection models.
Rule-derived features are excluded here as they are owned downstream by
Member 2's deterministic rule engine.

Feature Formulas:
1.  can_id:
    Formula: float32(ID)
    Raw CAN arbitration identifier.

2.  dlc:
    Formula: float32(DLC) in [0, 8]
    Data Length Code of the frame.

3.  is_extended:
    Formula: 1.0 if ID > 0x7FF (2047) else 0.0
    Indicator for 29-bit extended CAN arbitration identifiers.

4.  is_known_id:
    Formula: 1.0 if ID in Whitelist(train_normal) else 0.0
    Binary indicator whether arbitration ID was present in training normal traffic.

5.  id_rank:
    Formula: rank(ID) based on training normal frequency (1 for highest frequency, N+1 for unseen)
    Arbitration ID prevalence rank in normal baseline traffic.

6.  dt_global:
    Formula: dt_global(i) = t(i) - t(i-1) (0.0 for first frame)
    Inter-arrival elapsed time between consecutive frames across the entire bus.

7.  dt_same_id:
    Formula: dt_same_id(i) = t(i) - t_prev(ID) (0.0 on first occurrence of ID)
    Inter-arrival elapsed time since the previous frame with the identical arbitration ID.

8.  dt_ratio:
    Formula: dt_ratio(i) = dt_same_id(i) / mu_dt(ID) (1.0 if unseen or baseline mean <= 0)
    Ratio of observed cycle time to the baseline mean cycle time for this ID.

9.  dt_zscore:
    Formula: dt_zscore(i) = (dt_same_id(i) - mu_dt(ID)) / sigma_dt(ID) (0.0 if sigma=0 or unseen)
    Standard score of cycle time deviation from baseline normal parameters.

10. dt_roll_mean_20:
    Formula: (1 / K) * sum_{k=1}^K dt_same_id(k) for K = min(count(ID), 20)
    Short-term rolling mean cycle time over the last <= 20 frames of this ID.

11. dt_roll_std_20:
    Formula: sqrt((1 / (K - 1)) * sum_{k=1}^K (dt_same_id(k) - mean)^2) (0.0 if K < 2)
    Short-term rolling standard deviation of cycle time over last <= 20 frames of this ID.

12. msg_rate_50ms:
    Formula: count(frames j where t(i) - 0.050 <= t(j) <= t(i))
    Global bus message throughput within a backward-looking 50 ms time window.

13. id_count_100ms:
    Formula: count(frames j where ID(j) == ID(i) and t(i) - 0.100 <= t(j) <= t(i))
    Burst message count for this specific ID within a backward-looking 100 ms time window.

14. id_repetition_count:
    Formula: count(frames j in [max(0, i-49), i] where ID(j) == ID(i)) in [1, 50]
    Causal count of occurrences of this ID in the backward sliding window of the last 50 frames.

15. unique_ids_100ms:
    Formula: card({ID(j) : t(i) - 0.100 <= t(j) <= t(i)})
    Count of distinct active arbitration IDs within a backward-looking 100 ms time window.

16. payload_sum:
    Formula: sum_{k=0}^{dlc-1} data_k (0.0 if dlc == 0)
    Arithmetic sum of valid payload data bytes.

17. payload_nonzero:
    Formula: sum_{k=0}^{dlc-1} I(data_k != 0)
    Count of non-zero data bytes in the valid payload.

18. payload_entropy:
    Formula: -sum_{v in unique(payload)} p(v) * log2(p(v)) (0.0 if dlc <= 1)
    Shannon entropy of byte values in the valid payload.

19. hamming_prev_same_id:
    Formula: sum_{k=0}^{min(dlc_i, dlc_prev)-1} popcount(data_k(i) ^ data_k(prev))
    Bit-level Hamming distance from previous payload with identical CAN ID.

20. byte_change_ratio:
    Formula: (count_{k=0}^{max(dlc_i, dlc_prev)-1} I(data_k(i) != data_k(prev))) / max(dlc_i, 1)
    Fraction of payload bytes modified relative to previous frame with same CAN ID.
"""

from __future__ import annotations

from typing import Final

FEATURE_NAMES: Final[list[str]] = [
    "can_id",
    "dlc",
    "is_extended",
    "is_known_id",
    "id_rank",
    "dt_global",
    "dt_same_id",
    "dt_ratio",
    "dt_zscore",
    "dt_roll_mean_20",
    "dt_roll_std_20",
    "msg_rate_50ms",
    "id_count_100ms",
    "id_repetition_count",
    "unique_ids_100ms",
    "payload_sum",
    "payload_nonzero",
    "payload_entropy",
    "hamming_prev_same_id",
    "byte_change_ratio",
]

FEATURE_DESCRIPTIONS: Final[dict[str, str]] = {
    "can_id": "Raw CAN arbitration identifier: float32(ID)",
    "dlc": "Data Length Code: float32(DLC) in [0, 8]",
    "is_extended": "Extended 29-bit CAN ID flag: 1.0 if ID > 0x7FF else 0.0",
    "is_known_id": "Whitelist indicator: 1.0 if ID in normal training whitelist else 0.0",
    "id_rank": "Frequency rank from normal training baseline (1 = most frequent)",
    "dt_global": "Bus inter-arrival time: t(i) - t(i-1) in seconds",
    "dt_same_id": "Per-ID inter-arrival time: t(i) - t_prev(ID) in seconds",
    "dt_ratio": "Ratio of observed dt_same_id to baseline mean cycle time: dt_same_id / mu_dt",
    "dt_zscore": "Z-score of dt_same_id: (dt_same_id - mu_dt) / sigma_dt",
    "dt_roll_mean_20": "Causal rolling mean of dt_same_id over <= 20 previous frames of this ID",
    "dt_roll_std_20": "Causal rolling sample std of dt_same_id over <= 20 previous frames of this ID",
    "msg_rate_50ms": "Global bus frame count in backward-looking 50 ms window",
    "id_count_100ms": "Count of frames with this ID in backward-looking 100 ms window",
    "id_repetition_count": "Occurrences of this ID in backward-looking window of last 50 frames",
    "unique_ids_100ms": "Number of unique arbitration IDs in backward-looking 100 ms window",
    "payload_sum": "Sum of valid payload bytes: sum_{k=0}^{dlc-1} data_k",
    "payload_nonzero": "Count of non-zero bytes in valid payload",
    "payload_entropy": "Shannon entropy (base 2) over valid payload bytes",
    "hamming_prev_same_id": "Bitwise Hamming distance from previous frame with same ID",
    "byte_change_ratio": "Fraction of changed payload bytes relative to previous frame with same ID",
}


def get_feature_names() -> list[str]:
    """Return an immutable copy of the canonical model feature names.

    Returns:
        list[str]: The ordered list of 20 model features.
    """
    return list(FEATURE_NAMES)


def get_feature_count() -> int:
    """Return the total number of canonical model features.

    Returns:
        int: Number of features (20).
    """
    return len(FEATURE_NAMES)
