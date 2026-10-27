"""Unit tests for Stage 1 deterministic rules (src/stark/rules/definitions.py).

Verifies protocol rules:
- R1: Unknown / unauthorized CAN arbitration ID (r1_unknown_id)
- R2: Impossible inter-arrival time floor (r2_impossible_dt)
- R3: Bus flooding / frequency exceeded (r3_flooding)
- R4: Data Length Code (DLC) compliance violation (r4_dlc)
- R5: Repetition burst (r5_repetition)
- R6: Payload jump (r6_payload)
- R7: Message silence / timeout (r7_silence)
- RuleEngine: composite verdict arbitration
"""

from types import SimpleNamespace
import pytest

from stark.rules.definitions import (
    RULES,
    RuleHit,
    r1_unknown_id,
    r2_impossible_dt,
    r3_flooding,
    r4_dlc,
    r5_repetition,
    r6_payload,
    r7_silence,
    check_silence_timeouts,
)
from stark.rules.engine import RuleEngine, RuleVerdict
from stark.utils.exceptions import RuleConfigError


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


def test_r2_physical_min_dt_floor():
    """R2 enforces physical_min_dt (0.2ms) even when p01_dt * r2_factor is smaller."""
    bp = SimpleNamespace(p01_dt=0.00025)
    # 0.00025 * 0.4 = 0.00010s, which is below physical_min_dt 0.00020s (0.2ms)
    cfg = {"r2_factor": 0.4, "physical_min_dt": 0.00020}

    # Arrival at 0.15ms (0.00015s) is above 0.10ms but physically impossible on CAN (< 0.20ms)
    frame_impossible = {"can_id": 0x140, "dt_same_id": 0.00015}
    hit = r2_impossible_dt(frame_impossible, bp=bp, cfg=cfg)

    assert hit is not None
    assert hit.rule_id == "R2"
    assert hit.weight == 3
    assert hit.verdict == "VIOLATION"
    assert "below learned floor 0.2ms" in hit.reason


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


# ---------------------------------------------------------------------------
# Day 10: R7 + RuleEngine tests
# ---------------------------------------------------------------------------


def test_r7_silence_fires():
    """R7 fires when elapsed time exceeds p99_dt * r7_factor for a periodic ID."""
    # Nominal 10ms cycle; r7_factor=5.0 -> timeout = 50ms
    bp = SimpleNamespace(is_periodic=True, p99_dt=0.010)
    cfg = {"r7_factor": 5.0}

    # 200ms gap >> 50ms timeout -> fires
    frame = {"can_id": 0x140, "dt_same_id": 0.200}
    hit = r7_silence(frame, bp, cfg)

    assert hit is not None
    assert hit.rule_id == "R7"
    assert hit.weight == 1
    assert hit.verdict == "SUSPECT"
    assert hit.reason == "expected message missing for 200.0ms"


def test_r7_silence_quiet():
    """R7 stays quiet when elapsed time is within the watchdog ceiling."""
    bp = SimpleNamespace(is_periodic=True, p99_dt=0.010)
    cfg = {"r7_factor": 5.0}

    # 30ms gap < 50ms timeout -> stays quiet
    assert r7_silence({"can_id": 0x140, "dt_same_id": 0.030}, bp, cfg) is None

    # Aperiodic ID -> stays quiet regardless
    bp_aperiodic = SimpleNamespace(is_periodic=False, p99_dt=0.010)
    assert r7_silence({"can_id": 0x140, "dt_same_id": 9.9}, bp_aperiodic, cfg) is None

    # bp=None -> stays quiet
    assert r7_silence({"can_id": 0x140, "dt_same_id": 0.200}, None, cfg) is None


def test_r7_time_based_watchdog_monitoring():
    """R7 time-based watchdog detects missing messages even when no new frame arrives for that ID."""
    bp = SimpleNamespace(
        is_periodic={0x140: True, 0x260: True, 0x999: False},
        p99_dt={0x140: 0.010, 0x260: 0.020, 0x999: 0.050},
    )
    cfg = {"r7_factor": 4.0}

    # At t=1.000, 0x140 and 0x260 transmitted
    last_seen = {0x140: 1.000, 0x260: 1.000, 0x999: 1.000}

    # At t=1.020 (20ms later):
    # 0x140 timeout is 10ms * 4 = 40ms -> 20ms < 40ms -> no timeout
    # 0x260 timeout is 20ms * 4 = 80ms -> 20ms < 80ms -> no timeout
    hits_ok = check_silence_timeouts(last_seen, current_timestamp=1.020, bp=bp, cfg=cfg)
    assert len(hits_ok) == 0

    # At t=1.050 (50ms later):
    # 0x140 elapsed is 50ms > 40ms timeout -> FIRES R7!
    # 0x260 elapsed is 50ms < 80ms timeout -> quiet
    # 0x999 is aperiodic -> quiet
    hits_timeout = check_silence_timeouts(
        last_seen, current_timestamp=1.050, bp=bp, cfg=cfg
    )
    assert len(hits_timeout) == 1
    assert hits_timeout[0].rule_id == "R7"
    assert hits_timeout[0].weight == 1
    assert "watchdog timeout for 0x140" in hits_timeout[0].reason
    assert "elapsed 50.0ms exceeds 40.0ms" in hits_timeout[0].reason


def test_rules_list_has_all_seven():
    """RULES module-level list contains exactly all seven rule callables."""
    assert len(RULES) == 7
    rule_ids = {fn.__name__ for fn in RULES}
    assert rule_ids == {
        "r1_unknown_id",
        "r2_impossible_dt",
        "r3_flooding",
        "r4_dlc",
        "r5_repetition",
        "r6_payload",
        "r7_silence",
    }


# ---------------------------------------------------------------------------
# RuleEngine verdict arbitration tests
# ---------------------------------------------------------------------------


def _make_engine(cfg: dict, whitelist=None):
    """Helper: build RuleEngine with an optional in-memory profile."""
    profile = None
    if whitelist is not None:
        profile = SimpleNamespace(id_whitelist=whitelist)
    return RuleEngine(cfg=cfg, profile=profile)


def test_engine_violation_on_weight3_hit():
    """Verdict is VIOLATION when any weight-3 rule fires (e.g. R1)."""
    engine = _make_engine(cfg={}, whitelist=[0x260])  # 0x140 not in whitelist

    # Unknown ID -> R1 fires, weight 3 -> VIOLATION regardless of other rules
    frame = {"can_id": 0x140, "dlc": 8}
    verdict = engine.evaluate(frame)

    assert isinstance(verdict, RuleVerdict)
    assert verdict.verdict == "VIOLATION"
    assert verdict.score >= 3
    assert any(h.rule_id == "R1" for h in verdict.hits)


def test_engine_suspect_on_weight2_hit():
    """Verdict is SUSPECT for a single weight-2 hit (e.g. R4 DLC mismatch)."""
    # R4 only: known ID in whitelist, DLC mismatch
    profile = SimpleNamespace(
        id_whitelist=[0x140],
        p01_dt=0.010,
        p99_dt=0.010,
        is_periodic=True,
        modal_dlc=8,
        p995_rep=9,
        p99_hamming=48,
    )
    cfg = {
        "global_tuned_thresholds": {
            "r2_factor": 0.5,
            "r3_global_rate": 9999.0,
            "r7_factor": 5.0,
        }
    }
    engine = RuleEngine(
        cfg=cfg,
        profile=profile,
        # Restrict to R4 only to isolate the weight-2 hit
        rules=[r4_dlc],
    )

    frame = {"can_id": 0x140, "dlc": 4}  # DLC mismatch
    verdict = engine.evaluate(frame)

    assert verdict.verdict == "SUSPECT"
    assert verdict.score == 2
    assert len(verdict.hits) == 1
    assert verdict.hits[0].rule_id == "R4"


def test_engine_clean_when_nothing_fires():
    """Verdict is CLEAN when no rules fire on a fully compliant frame."""
    profile = SimpleNamespace(
        id_whitelist=[0x140],
        p01_dt=0.010,
        p99_dt=0.010,
        is_periodic=True,
        modal_dlc=8,
        p995_rep=9,
        p99_hamming=48,
    )
    cfg = {
        "global_tuned_thresholds": {
            "r2_factor": 0.5,
            "r3_global_rate": 9999.0,
            "r7_factor": 5.0,
        }
    }
    engine = RuleEngine(cfg=cfg, profile=profile)

    frame = {"can_id": 0x140, "dlc": 8, "dt_same_id": 0.010}
    verdict = engine.evaluate(frame)

    assert verdict.verdict == "CLEAN"
    assert verdict.score == 0
    assert verdict.hits == []


def test_engine_clean_on_lone_r7_hit():
    """A lone R7 hit (score=1, no weight-3) stays CLEAN per spec §2.2."""
    profile = SimpleNamespace(
        id_whitelist=[0x140],
        p01_dt=0.010,
        p99_dt=0.010,
        is_periodic=True,
        modal_dlc=8,
        p995_rep=9,
        p99_hamming=48,
    )
    cfg = {
        "global_tuned_thresholds": {
            "r2_factor": 0.5,
            "r3_global_rate": 9999.0,
            "r7_factor": 5.0,
        }
    }
    engine = RuleEngine(cfg=cfg, profile=profile, rules=[r7_silence])

    # 200ms gap triggers R7 (weight 1, score 1) -> CLEAN not SUSPECT
    frame = {"can_id": 0x140, "dt_same_id": 0.200}
    verdict = engine.evaluate(frame)

    assert verdict.verdict == "CLEAN"  # score=1 < 2 and no weight-3 hit
    assert verdict.score == 1
    assert len(verdict.hits) == 1
    assert verdict.hits[0].rule_id == "R7"


def test_engine_from_yaml(tmp_path):
    """RuleEngine.from_yaml loads a valid rules.yaml and evaluates a frame.

    When no profile is supplied, R1 fires for every ID (no whitelist) and the
    verdict is VIOLATION.  Pass a minimal profile to test the happy path.
    """
    rules_yaml = tmp_path / "rules.yaml"
    rules_yaml.write_text(
        "global_tuned_thresholds:\n"
        "  r2_factor: 0.5\n"
        "  r3_global_rate: 9999.0\n"
        "  r7_factor: 5.0\n"
        "per_id_baselines:\n"
        "  id_whitelist: [320]\n",
        encoding="utf-8",
    )

    # Without a profile every ID is unknown -> R1 fires -> VIOLATION
    engine_no_profile = RuleEngine.from_yaml(rules_yaml)
    verdict_no_profile = engine_no_profile.evaluate({"can_id": 0x140, "dlc": 8})
    assert verdict_no_profile.verdict == "VIOLATION"
    assert any(h.rule_id == "R1" for h in verdict_no_profile.hits)

    # With a profile that whitelists 0x140 (=320) -> R1 silent -> CLEAN
    profile = SimpleNamespace(id_whitelist=[0x140], modal_dlc=8, is_periodic=False)
    engine_with_profile = RuleEngine.from_yaml(rules_yaml, profile=profile)
    verdict_ok = engine_with_profile.evaluate({"can_id": 0x140, "dlc": 8})
    assert verdict_ok.verdict == "CLEAN"


def test_engine_from_yaml_missing_file():
    """RuleEngine.from_yaml raises RuleConfigError for a non-existent file."""
    with pytest.raises(RuleConfigError, match="not found"):
        RuleEngine.from_yaml("/nonexistent/path/rules.yaml")


def test_engine_from_yaml_malformed(tmp_path):
    """RuleEngine.from_yaml raises RuleConfigError for YAML missing required keys."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("only_wrong_key: 1\n", encoding="utf-8")
    with pytest.raises(RuleConfigError, match="missing required top-level keys"):
        RuleEngine.from_yaml(bad_yaml)
