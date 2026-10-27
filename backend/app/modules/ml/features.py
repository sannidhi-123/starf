"""Feature extraction shared by training and inference.

Raw features per frame: [log1p(delta_t in ms), dlc, byte_entropy, log1p(frequency Hz),
mean payload byte / 255, max payload byte / 255].
Missing delta_t / frequency / entropy are derived from the frame stream (per CAN ID)
or left as NaN and imputed with the training means stored in the model artifact.
"""

import math
from collections import Counter
from typing import List, Sequence

import numpy as np

from app.modules.detection.schemas import CANFrameInput

FEATURE_NAMES = ["delta_t_log", "dlc", "byte_entropy", "frequency_log", "payload_mean", "payload_max"]


def payload_entropy(payload_bytes: Sequence[int]) -> float:
    if not payload_bytes:
        return 0.0
    n = len(payload_bytes)
    return -sum((c / n) * math.log2(c / n) for c in Counter(payload_bytes).values())


def frames_to_matrix(frames: Sequence[CANFrameInput]) -> np.ndarray:
    """Return an (n, 4) float matrix; unknown values are NaN. Frames are read in the given order."""
    last_ts: dict[int, float] = {}
    rows: List[List[float]] = []
    for f in frames:
        delta_t = f.delta_t
        if delta_t is None and f.can_id in last_ts:
            delta_t = max(f.timestamp - last_ts[f.can_id], 0.0)
        last_ts[f.can_id] = f.timestamp
        frequency = f.frequency
        if frequency is None and delta_t:
            frequency = 1.0 / delta_t
        entropy = f.byte_entropy if f.byte_entropy is not None else payload_entropy(f.payload_bytes)
        data = f.payload_bytes
        rows.append(
            [
                math.log1p(delta_t * 1000.0) if delta_t is not None else math.nan,
                float(f.dlc),
                float(entropy),
                math.log1p(frequency) if frequency is not None else math.nan,
                sum(data) / len(data) / 255.0 if data else 0.0,
                max(data) / 255.0 if data else 0.0,
            ]
        )
    return np.array(rows, dtype=float).reshape(len(rows), len(FEATURE_NAMES))
