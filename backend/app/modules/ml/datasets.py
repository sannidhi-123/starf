"""Training-data providers.

The dataset module owns real datasets. Until it exposes a loader, `SyntheticDatasetProvider`
generates a deterministic labeled CAN stream (normal / DoS / fuzzy) so the ML workflow runs
end-to-end in mock mode. Swap it by passing another `DatasetProvider` to `MLService`.
"""

import zlib
from typing import List, Protocol

import numpy as np

from app.modules.detection.schemas import CANFrameInput
from app.modules.ml.features import payload_entropy
from app.modules.ml.schemas import LabeledFrame


class DatasetProvider(Protocol):
    source: str

    def load(self, dataset_id: str) -> List[LabeledFrame]: ...


class SyntheticDatasetProvider:
    source = "synthetic"

    def __init__(self, size: int = 1500) -> None:
        self.size = size

    def load(self, dataset_id: str) -> List[LabeledFrame]:
        rng = np.random.default_rng(zlib.crc32(dataset_id.encode()))
        t = 0.0
        out: List[LabeledFrame] = []
        for _ in range(self.size):
            kind = rng.choice(["normal", "dos", "fuzzy"], p=[0.8, 0.1, 0.1])
            if kind == "normal":
                dt, can_id = max(rng.normal(0.01, 0.002), 0.002), int(rng.choice([0x100, 0x1F0, 0x2A0]))
                payload = [int(v) for v in rng.integers(0, 64, size=8)]
            elif kind == "dos":
                dt, can_id, payload = max(rng.normal(0.0003, 0.0001), 0.00005), 0x000, [0] * 8
            else:
                dt, can_id = float(rng.uniform(0.0005, 0.03)), int(rng.integers(0, 0x800))
                payload = [int(v) for v in rng.integers(0, 256, size=8)]
            t += dt
            out.append(
                LabeledFrame(
                    frame=CANFrameInput(
                        timestamp=t,
                        can_id=can_id,
                        dlc=8,
                        payload=payload,
                        delta_t=float(dt),
                        byte_entropy=min(payload_entropy(payload), 8.0),
                    ),
                    label=0 if kind == "normal" else 1,
                )
            )
        return out
