"""STARK Stage 1 deterministic rule definitions and arbitration models."""

from stark.rules.definitions import (
    FEATURE_CAN_ID,
    FEATURE_DELTA_T,
    FEATURE_DLC,
    FEATURE_HAMMING_DISTANCE,
    FEATURE_MSG_RATE_50MS,
    FEATURE_REPETITION_COUNT,
    RULES,
    RuleHit,
    r1_unknown_id,
    r2_impossible_dt,
    r3_flooding,
    r4_dlc,
    r5_repetition,
    r6_payload,
    r7_silence,
)
from stark.rules.engine import RuleEngine, RuleVerdict

__all__ = [
    "FEATURE_CAN_ID",
    "FEATURE_DELTA_T",
    "FEATURE_DLC",
    "FEATURE_HAMMING_DISTANCE",
    "FEATURE_MSG_RATE_50MS",
    "FEATURE_REPETITION_COUNT",
    "RULES",
    "RuleHit",
    "RuleEngine",
    "RuleVerdict",
    "r1_unknown_id",
    "r2_impossible_dt",
    "r3_flooding",
    "r4_dlc",
    "r5_repetition",
    "r6_payload",
    "r7_silence",
]
