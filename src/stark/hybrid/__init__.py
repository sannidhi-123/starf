"""STARK Hybrid Fusion module.

Arbitrates Stage 1 deterministic rule verdicts and Stage 2 ML predictions,
tracks multi-frame state, and computes operational severity scores.
"""

from __future__ import annotations

from stark.hybrid.fusion import (
    TAU_HI,
    TAU_LO,
    Decision,
    FusionState,
    decide,
)
from stark.hybrid.severity import score

__all__ = [
    "Decision",
    "FusionState",
    "TAU_HI",
    "TAU_LO",
    "decide",
    "score",
]
