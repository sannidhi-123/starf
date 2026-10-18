"""Unit tests for Stage 1 deterministic rules (src/stark/rules/definitions.py).

Verifies protocol rules:
- R1: Unknown / unauthorized CAN arbitration ID (r1_unknown_id)
- R4: Data Length Code (DLC) compliance violation (r4_dlc)
"""

from types import SimpleNamespace
import pytest

from stark.rules.definitions import RuleHit, r1_unknown_id, r4_dlc


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
