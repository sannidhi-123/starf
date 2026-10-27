"""Tests for Hybrid Fusion arbitration, Severity scoring, and Stage2Model stub."""

from __future__ import annotations

import pytest

from stark.hybrid.fusion import (
    TAU_HI,
    TAU_LO,
    Decision,
    FusionState,
    decide,
)
from stark.hybrid.severity import score
from stark.ml.predict import Stage2Model, predict
from stark.rules.definitions import RuleHit
from stark.rules.engine import RuleVerdict

# ============================================================================
# Stage2Model Stub Tests
# ============================================================================


def test_stage2_model_deterministic_can_id_zero():
    """can_id == 0 triggers deterministic 'dos'."""
    model = Stage2Model()
    cls, probs = model.predict({"can_id": 0})
    assert cls == "dos"
    assert probs["dos"] == pytest.approx(0.93)
    assert probs["normal"] == pytest.approx(0.03)
    assert probs["fuzzy"] == pytest.approx(0.02)
    assert probs["spoofing"] == pytest.approx(0.02)


def test_stage2_model_deterministic_dt_floor():
    """dt_same_id < 0.0005 triggers deterministic 'dos'."""
    model = Stage2Model()
    cls, probs = model.predict({"can_id": 0x100, "dt_same_id": 0.0002})
    assert cls == "dos"
    assert probs["dos"] == pytest.approx(0.93)


def test_stage2_model_deterministic_normal():
    """Standard frame without anomaly features returns 'normal'."""
    model = Stage2Model()
    cls, probs = model.predict({"can_id": 0x100, "dt_same_id": 0.02})
    assert cls == "normal"
    assert probs["normal"] == pytest.approx(0.97)
    assert probs["dos"] == pytest.approx(0.01)


def test_stage2_model_object_input():
    """Stage2Model accepts attribute-based object representation."""

    class MockFrame:
        can_id = 0
        dt_same_id = 0.01

    model = Stage2Model()
    cls, probs = model.predict(MockFrame())
    assert cls == "dos"
    assert probs["dos"] == pytest.approx(0.93)


def test_stage2_model_random_mode_with_seed():
    """Optional seed parameter generates valid normalized distribution in random mode."""
    model = Stage2Model(seed=42, random_mode=True)
    cls, probs = model.predict({"can_id": 0x200})
    assert cls in ("normal", "dos", "fuzzy", "spoofing")
    assert sum(probs.values()) == pytest.approx(1.0)


def test_constants_and_predict_function():
    """Verify TAU_HI, TAU_LO threshold constants and functional predict() wrapper."""
    assert TAU_HI == 0.85
    assert TAU_LO == 0.50

    cls, probs = predict({"can_id": 0})
    assert cls == "dos"
    assert probs["dos"] == pytest.approx(0.93)


# ============================================================================
# Hybrid Fusion 7-Row Arbitration Tests
# ============================================================================


def test_row_1_violation_and_attack():
    """Row 1: VIOLATION and class != normal -> label=class, conf=0.5+0.5*p, stage 'both'."""
    hit = RuleHit(rule_id="R1", reason="Unknown CAN ID", weight=3, verdict="VIOLATION")
    rv = RuleVerdict(verdict="VIOLATION", score=3, hits=[hit])

    p = 0.90
    d = decide(rv, stage2_class="dos", stage2_prob=p)

    assert d.label == "dos"
    assert d.confidence == pytest.approx(0.5 + 0.5 * p)
    assert d.stage == "both"
    assert d.severity_cap is None
    assert d.rule_ids == ["R1"]


def test_row_2_violation_and_normal():
    """Row 2: VIOLATION and class == normal -> label 'ATTACK (unclassified)', conf 0.70, stage 'stage1'."""
    hit = RuleHit(
        rule_id="R1",
        reason="Unauthorized arbitration ID",
        weight=3,
        verdict="VIOLATION",
    )
    rv = RuleVerdict(verdict="VIOLATION", score=3, hits=[hit])

    # Explicit requirement: R1 VIOLATION + normal 0.97
    d = decide(rv, stage2_class="normal", stage2_prob=0.97)

    assert d.label == "ATTACK (unclassified)"
    assert d.confidence == pytest.approx(0.70)
    assert d.stage == "stage1"
    assert d.severity_cap is None
    assert d.rule_ids == ["R1"]


def test_row_3_suspect_high_confidence():
    """Row 3: SUSPECT and class != normal and p >= 0.85 -> label=class, conf=p, stage 'both'."""
    hit = RuleHit(rule_id="R5", reason="Repetition burst", weight=2, verdict="SUSPECT")
    rv = RuleVerdict(verdict="SUSPECT", score=2, hits=[hit])

    p = 0.88
    d = decide(rv, stage2_class="spoofing", stage2_prob=p)

    assert d.label == "spoofing"
    assert d.confidence == pytest.approx(p)
    assert d.stage == "both"
    assert d.severity_cap is None
    assert d.rule_ids == ["R5"]


def test_row_4_suspect_moderate_confidence():
    """Row 4: SUSPECT and class != normal and 0.50 <= p < 0.85 -> label=class, conf=p, stage 'stage2', severity_cap 'MEDIUM'."""
    hit = RuleHit(rule_id="R5", reason="Burst", weight=2, verdict="SUSPECT")
    rv = RuleVerdict(verdict="SUSPECT", score=2, hits=[hit])

    p = 0.72
    d = decide(rv, stage2_class="fuzzy", stage2_prob=p)

    assert d.label == "fuzzy"
    assert d.confidence == pytest.approx(p)
    assert d.stage == "stage2"
    assert d.severity_cap == "MEDIUM"
    assert d.rule_ids == ["R5"]


def test_row_5_suspect_normal_isolated():
    """Row 5: SUSPECT and class == normal without persistent repetition filters to 'normal'."""
    hit = RuleHit(rule_id="R6", reason="Payload jump", weight=1, verdict="SUSPECT")
    rv = RuleVerdict(verdict="SUSPECT", score=2, hits=[hit])

    d = decide(rv, stage2_class="normal", stage2_prob=0.95)

    assert d.label == "normal"
    assert d.stage == "stage2"
    assert d.severity_cap is None


def test_row_5_persistence_burst_and_spread():
    """Row 5 persistence test:

    Hits at t=0.0, 0.4, 0.9 on ID 0x2C0 -> SUSPICIOUS (>= 3 within 1s).
    Spread over 3s (t=0.0, 1.5, 3.0) on ID 0x2C0 -> normal.
    """
    hit = RuleHit(rule_id="R5", reason="Timing burst", weight=2, verdict="SUSPECT")
    rv = RuleVerdict(verdict="SUSPECT", score=2, hits=[hit])

    # Scenario A: 3 hits within 1 second (0.0s, 0.4s, 0.9s)
    state = FusionState(window_sec=1.0)
    can_id = 0x2C0

    d0 = decide(rv, "normal", 0.95, can_id=can_id, timestamp=0.0, state=state)
    assert d0.label == "normal"

    d1 = decide(rv, "normal", 0.95, can_id=can_id, timestamp=0.4, state=state)
    assert d1.label == "normal"

    d2 = decide(rv, "normal", 0.95, can_id=can_id, timestamp=0.9, state=state)
    assert d2.label == "SUSPICIOUS"
    assert d2.confidence == pytest.approx(0.40)
    assert d2.stage == "stage1_persistent"
    assert d2.severity_cap is None
    assert d2.rule_ids == ["R5"]

    # Scenario B: 3 hits spread over 3 seconds (0.0s, 1.5s, 3.0s) -> filtered to normal
    state_spread = FusionState(window_sec=1.0)

    s0 = decide(rv, "normal", 0.95, can_id=can_id, timestamp=0.0, state=state_spread)
    assert s0.label == "normal"

    s1 = decide(rv, "normal", 0.95, can_id=can_id, timestamp=1.5, state=state_spread)
    assert s1.label == "normal"

    s2 = decide(rv, "normal", 0.95, can_id=can_id, timestamp=3.0, state=state_spread)
    assert s2.label == "normal"
    assert s2.stage == "stage2"


def test_row_6_clean_sampled_attack():
    """Row 6: CLEAN and sampled and class != normal and p >= 0.90 -> label=class, conf=p, stage 'stage2'."""
    rv = RuleVerdict(verdict="CLEAN", score=0, hits=[])

    p = 0.94
    d = decide(rv, stage2_class="dos", stage2_prob=p, sampled=True)

    assert d.label == "dos"
    assert d.confidence == pytest.approx(p)
    assert d.stage == "stage2"
    assert d.severity_cap is None

    # Unsampled CLEAN frame must not trigger Row 6; falls to Row 7
    d_unsampled = decide(rv, stage2_class="dos", stage2_prob=p, sampled=False)
    assert d_unsampled.label == "normal"
    assert d_unsampled.confidence == pytest.approx(1.0)
    assert d_unsampled.stage == "stage1"


def test_row_7_clean_otherwise():
    """Row 7: CLEAN otherwise -> 'normal', conf 1.0, stage 'stage1'."""
    rv = RuleVerdict(verdict="CLEAN", score=0, hits=[])

    d = decide(rv, stage2_class="normal", stage2_prob=0.98, sampled=False)

    assert d.label == "normal"
    assert d.confidence == pytest.approx(1.0)
    assert d.stage == "stage1"
    assert d.severity_cap is None
    assert d.rule_ids == []


# ============================================================================
# Boundary Tests (p = 0.85, p = 0.50, p = 0.90)
# ============================================================================


def test_boundary_p_0_85():
    """Boundary test around TAU_HI = 0.85 (Row 3 vs Row 4)."""
    hit = RuleHit(rule_id="R5", reason="Burst", weight=2, verdict="SUSPECT")
    rv = RuleVerdict(verdict="SUSPECT", score=2, hits=[hit])

    # Exactly at 0.85: Row 3 fires
    d_hi = decide(rv, stage2_class="spoofing", stage2_prob=0.85)
    assert d_hi.label == "spoofing"
    assert d_hi.stage == "both"
    assert d_hi.severity_cap is None
    assert d_hi.confidence == pytest.approx(0.85)

    # Just below 0.85: Row 4 fires
    d_lo = decide(rv, stage2_class="spoofing", stage2_prob=0.8499)
    assert d_lo.label == "spoofing"
    assert d_lo.stage == "stage2"
    assert d_lo.severity_cap == "MEDIUM"
    assert d_lo.confidence == pytest.approx(0.8499)


def test_boundary_p_0_50():
    """Boundary test around TAU_LO = 0.50 (Row 4 vs Row 5)."""
    hit = RuleHit(rule_id="R5", reason="Burst", weight=2, verdict="SUSPECT")
    rv = RuleVerdict(verdict="SUSPECT", score=2, hits=[hit])

    # Exactly at 0.50: Row 4 fires
    d_4 = decide(rv, stage2_class="fuzzy", stage2_prob=0.50)
    assert d_4.label == "fuzzy"
    assert d_4.stage == "stage2"
    assert d_4.severity_cap == "MEDIUM"
    assert d_4.confidence == pytest.approx(0.50)

    # Just below 0.50: Row 5 fires (filtered to normal without persistence)
    d_5 = decide(rv, stage2_class="fuzzy", stage2_prob=0.4999)
    assert d_5.label == "normal"
    assert d_5.stage == "stage2"
    assert d_5.severity_cap is None


def test_boundary_p_0_90():
    """Boundary test around TAU_CLEAN_SAMPLE = 0.90 (Row 6 vs Row 7)."""
    rv = RuleVerdict(verdict="CLEAN", score=0, hits=[])

    # Exactly at 0.90 with sampled=True: Row 6 fires
    d_6 = decide(rv, stage2_class="dos", stage2_prob=0.90, sampled=True)
    assert d_6.label == "dos"
    assert d_6.stage == "stage2"
    assert d_6.confidence == pytest.approx(0.90)

    # Just below 0.90 with sampled=True: Row 7 fires
    d_7 = decide(rv, stage2_class="dos", stage2_prob=0.8999, sampled=True)
    assert d_7.label == "normal"
    assert d_7.stage == "stage1"
    assert d_7.confidence == pytest.approx(1.0)


# ============================================================================
# Severity Scoring Tests (CRITICAL & MEDIUM cap)
# ============================================================================


def test_severity_critical():
    """Severity score >= 9 evaluates to CRITICAL.

    base(dos)=3 + min(3, rule_score=3)=3 + conf(0.95 >= 0.9)=2 + persist(stage1_persistent)=3
    Total score = 11 -> CRITICAL.
    """
    decision = Decision(
        label="dos",
        confidence=0.95,
        stage="stage1_persistent",
        severity_cap=None,
        rule_ids=["R1"],
    )
    rv = RuleVerdict(
        verdict="VIOLATION", score=3, hits=[RuleHit("R1", "Unknown ID", 3)]
    )

    score_val, level = score(decision, rv, can_id=0x100)
    assert score_val == 11
    assert level == "CRITICAL"


def test_severity_medium_cap():
    """Severity level clamped to at most MEDIUM when severity_cap == 'MEDIUM'.

    base(fuzzy)=3 + min(3, rule_score=3)=3 + conf(0.80 >= 0.7)=1 + persist=0
    Raw score = 7 (which is ordinarily HIGH, range 6-8).
    Due to severity_cap='MEDIUM', level must be clamped to 'MEDIUM'.
    """
    decision = Decision(
        label="fuzzy",
        confidence=0.80,
        stage="stage2",
        severity_cap="MEDIUM",
        rule_ids=["R5"],
    )
    rv = RuleVerdict(verdict="SUSPECT", score=3, hits=[RuleHit("R2", "Floor", 3)])

    score_val, level = score(decision, rv, can_id=0x200)
    assert score_val == 7
    assert level == "MEDIUM"


def test_severity_levels_comprehensive():
    """Verify tier coverage across NONE, LOW, MEDIUM, HIGH."""
    # NONE (0)
    d_none = Decision(label="normal", confidence=0.0, stage="stage1")
    rv_clean = RuleVerdict(verdict="CLEAN", score=0, hits=[])
    s_none, lvl_none = score(d_none, rv_clean, 0x100)
    assert s_none == 0
    assert lvl_none == "NONE"

    # LOW (1-2)
    d_low = Decision(label="SUSPICIOUS", confidence=0.40, stage="stage1")
    s_low, lvl_low = score(d_low, rv_clean, 0x100)
    assert s_low == 1
    assert lvl_low == "LOW"

    # MEDIUM (3-5)
    d_med = Decision(label="normal", confidence=0.0, stage="stage1_persistent")
    s_med, lvl_med = score(d_med, rv_clean, 0x100)
    assert s_med == 3
    assert lvl_med == "MEDIUM"

    # HIGH (6-8)
    d_high = Decision(label="spoofing", confidence=0.75, stage="stage2")
    rv_sus = RuleVerdict(verdict="SUSPECT", score=2, hits=[])
    s_high, lvl_high = score(d_high, rv_sus, 0x100)
    assert s_high == 6
    assert lvl_high == "HIGH"
