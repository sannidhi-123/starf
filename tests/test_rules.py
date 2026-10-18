"""Unit tests for Stage 1 deterministic rules (src/stark/rules/definitions.py).

Verifies protocol rules:
- R1: Unknown / unauthorized CAN arbitration ID (r1_unknown_id)
- R2: Impossible inter-arrival time floor (r2_impossible_dt)
- R3: Bus flooding / frequency exceeded (r3_flooding)
- R4: Data Length Code (DLC) compliance violation (r4_dlc)
"""

from types import SimpleNamespace
import pytest

from stark.rules.definitions import (
    RuleHit,
    r1_unknown_id,
    r2_impossible_dt,
    r3_flooding,
    r4_dlc,
    r5_repetition,
    r6_payload,
)


def test_rule_hit_dataclass():
    """Verify RuleHit is frozen and assigns appropriate default verdicts."""
    h1 = RuleHit(rule_id="R1", reason="unknown CAN ID 0x999", weight=3)
    assert h1.rule_id == "R1"
    assert h1.reason == "unknown CAN ID 0x999"
    assert h1.weight == 3
    assert h1.verdict == "VIOLATION"

    h4 = RuleHit(rule_id="R4", reason="DLC 4 != expected 8 for 0x140", weight=2)
    assert h4.rule_id == "R4"
    assert h4.weight == 2
    assert h4.verdict == "SUSPECT"

    # Verify frozen immutability
    with pytest.raises(Exception):
        h1.weight = 1  # type: ignore


def test_r1_unseen_id():
    """R1 fires on an unseen CAN ID (bp is None or ID not in whitelist)."""
    # Unseen ID with bp=None
    unseen_frame = {"can_id": 0x999, "dlc": 8}
    hit = r1_unknown_id(unseen_frame, bp=None)

    assert hit is not None
    assert hit.rule_id == "R1"
    assert hit.weight == 3
    assert hit.verdict == "VIOLATION"
    assert hit.reason == "unknown CAN ID 0x999"

    # Unseen ID with whitelist provided in bp
    bp_with_whitelist = SimpleNamespace(id_whitelist=[0x140, 0x260, 0x316])
    hit2 = r1_unknown_id(unseen_frame, bp=bp_with_whitelist)
    assert hit2 is not None
    assert hit2.rule_id == "R1"
    assert hit2.weight == 3
    assert hit2.reason == "unknown CAN ID 0x999"


def test_r1_known_id():
    """R1 stays quiet on a known CAN ID present in the whitelist."""
    known_frame = {"can_id": 0x140, "dlc": 8}
    bp_known = SimpleNamespace(id_whitelist=[0x140, 0x260, 0x316])

    hit = r1_unknown_id(known_frame, bp=bp_known)
    assert hit is None

    # Also stays quiet when bp represents a per-ID profile for this valid ID
    per_id_bp = SimpleNamespace(can_id=0x140, modal_dlc=8)
    hit_per_id = r1_unknown_id(known_frame, bp=per_id_bp)
    assert hit_per_id is None


def test_r2_impossible_dt_fires():
    """R2 fires when dt_same_id is below learned floor (0.4x p01_dt)."""
    # Nominal 10ms cycle, r2_factor 0.5 -> floor is 5.0ms
    bp = SimpleNamespace(p01_dt=0.010)
    cfg = {"r2_factor": 0.5}

    # At 0.4x p01 (4.0ms), fires violation below learned floor 5.0ms
    frame_fast = {"can_id": 0x140, "dt_same_id": 0.004}
    hit = r2_impossible_dt(frame_fast, bp=bp, cfg=cfg)

    assert hit is not None
    assert hit.rule_id == "R2"
    assert hit.weight == 3
    assert hit.verdict == "VIOLATION"
    assert hit.reason == "Δt=4.0ms below learned floor 5.0ms"


def test_r2_impossible_dt_quiet():
    """R2 stays quiet when dt_same_id is above learned floor (1.1x p01_dt)."""
    bp = SimpleNamespace(p01_dt=0.010)
    cfg = {"r2_factor": 0.5}

    # At 1.1x p01 (11.0ms), well above 5.0ms floor -> stays quiet
    frame_normal = {"can_id": 0x140, "dt_same_id": 0.011}
    hit = r2_impossible_dt(frame_normal, bp=bp, cfg=cfg)
    assert hit is None

    # Stays quiet when bp is None (R1 handles unseen IDs)
    assert r2_impossible_dt(frame_normal, bp=None, cfg=cfg) is None

    # Stays quiet when dt_same_id is missing (e.g. initial frame)
    assert r2_impossible_dt({"can_id": 0x140}, bp=bp, cfg=cfg) is None


def test_r3_flooding_fires():
    """R3 fires when msg_rate_50ms exceeds cfg.r3_global_rate."""
    cfg = {"r3_global_rate": 15.0}

    # Burst above global threshold (e.g. 25 frames in 50ms)
    frame_flooding = {"msg_rate_50ms": 25.0}

    # Must work even when bp is None (ID-independent)
    hit = r3_flooding(frame_flooding, bp=None, cfg=cfg)

    assert hit is not None
    assert hit.rule_id == "R3"
    assert hit.weight == 3
    assert hit.verdict == "VIOLATION"
    assert hit.reason == "bus rate 25 msgs/50ms exceeds 15"


def test_r3_flooding_quiet():
    """R3 stays quiet when bus rate is below global threshold."""
    cfg = {"r3_global_rate": 15.0}

    frame_normal = {"msg_rate_50ms": 10.0}
    hit = r3_flooding(frame_normal, bp=None, cfg=cfg)
    assert hit is None

    # Stays quiet when msg_rate_50ms is missing
    assert r3_flooding({}, bp=None, cfg=cfg) is None


def test_r4_dlc_mismatch():
    """R4 fires on a DLC mismatch against modal_dlc or outside [0, 8] bounds."""
    # Mismatch against expected modal DLC (observed 4, expected 8)
    frame_mismatch = {"can_id": 0x140, "dlc": 4}
    bp = SimpleNamespace(modal_dlc=8)

    hit = r4_dlc(frame_mismatch, bp=bp)
    assert hit is not None
    assert hit.rule_id == "R4"
    assert hit.weight == 2
    assert hit.verdict == "SUSPECT"
    assert hit.reason == "DLC 4 != expected 8 for 0x140"

    # Physical domain bound violation: DLC > 8 (e.g. DLC=9)
    frame_overflow = {"can_id": 0x140, "dlc": 9}
    hit_overflow = r4_dlc(frame_overflow, bp=bp)
    assert hit_overflow is not None
    assert hit_overflow.rule_id == "R4"
    assert hit_overflow.reason == "DLC 9 != expected 8 for 0x140"

    # Physical domain bound violation: DLC < 0 (e.g. DLC=-1)
    frame_negative = {"can_id": 0x140, "dlc": -1}
    hit_neg = r4_dlc(frame_negative, bp=bp)
    assert hit_neg is not None
    assert hit_neg.rule_id == "R4"
    assert hit_neg.reason == "DLC -1 != expected 8 for 0x140"


def test_r4_dlc_match():
    """R4 stays quiet on a match where observed DLC equals expected modal DLC."""
    frame_match = {"can_id": 0x140, "dlc": 8}
    bp = SimpleNamespace(modal_dlc=8)

    hit = r4_dlc(frame_match, bp=bp)
    assert hit is None

    # Also stays quiet on legitimate zero-DLC frame if modal is 0
    zero_frame = {"can_id": 0x050, "dlc": 0}
    bp_zero = SimpleNamespace(modal_dlc=0)
    hit_zero = r4_dlc(zero_frame, bp=bp_zero)
    assert hit_zero is None


def test_r5_repetition_fires():
    """R5 fires on 37 repeats against a p99.5 of 9."""
    f = {"id_repetition_count": 37}
    bp = SimpleNamespace(p995_rep=9)

    hit = r5_repetition(f, bp)
    assert hit is not None
    assert hit.rule_id == "R5"
    assert hit.weight == 2
    assert hit.verdict == "SUSPECT"
    assert hit.reason == "37 repeats in last 50 frames (p99.5=9)"


def test_r5_repetition_quiet():
    """R5 stays quiet when repetition count is below or equal to threshold."""
    bp = SimpleNamespace(p995_rep=9)

    # 5 repeats <= 9 -> stays quiet
    assert r5_repetition({"id_repetition_count": 5}, bp) is None
    # 9 repeats <= 9 -> stays quiet
    assert r5_repetition({"id_repetition_count": 9}, bp) is None
    # Missing feature or bp=None
    assert r5_repetition({}, bp) is None
    assert r5_repetition({"id_repetition_count": 37}, None) is None


def test_r6_payload_fires():
    """R6 fires on a 22-bit jump against a p99 of 6 for a periodic ID."""
    f = {"can_id": 0x140, "hamming_prev_same_id": 22}
    bp = SimpleNamespace(is_periodic=True, p99_hamming=6)

    hit = r6_payload(f, bp)
    assert hit is not None
    assert hit.rule_id == "R6"
    assert hit.weight == 2
    assert hit.verdict == "SUSPECT"
    assert hit.reason == "payload jumped 22 bits (p99=6)"


def test_r6_payload_quiet_aperiodic():
    """R6 stays quiet when the ID is not periodic even if Hamming jump is large."""
    f = {"can_id": 0x140, "hamming_prev_same_id": 22}
    # ID is event-triggered / aperiodic
    bp_aperiodic = SimpleNamespace(is_periodic=False, p99_hamming=6)

    hit = r6_payload(f, bp_aperiodic)
    assert hit is None


def test_r6_payload_quiet_normal():
    """R6 stays quiet when bitwise Hamming distance is below or equal to threshold."""
    bp = SimpleNamespace(is_periodic=True, p99_hamming=6)

    # 4-bit jump <= 6 -> stays quiet
    assert r6_payload({"can_id": 0x140, "hamming_prev_same_id": 4}, bp) is None
    # 6-bit jump <= 6 -> stays quiet
    assert r6_payload({"can_id": 0x140, "hamming_prev_same_id": 6}, bp) is None
    # Missing feature or bp=None
    assert r6_payload({"can_id": 0x140}, bp) is None
    assert r6_payload({"can_id": 0x140, "hamming_prev_same_id": 22}, None) is None
