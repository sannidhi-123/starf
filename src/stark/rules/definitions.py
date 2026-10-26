"""Stage 1 deterministic rule definitions for CAN-Bus anomaly detection.

Implements protocol rules:
- R1: Unknown / unauthorized CAN arbitration ID (r1_unknown_id)
- R2: Impossible inter-arrival time floor (r2_impossible_dt)
- R3: Bus flooding / frequency exceeded (r3_flooding)
- R4: Data Length Code (DLC) compliance violation (r4_dlc)

Conforms to docs/rule_spec.md and config/rules.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

# Module-level feature names for contract compatibility with Person 1's feature registry
# Any renaming in Person 1's registry is a one-line fix here.
FEATURE_CAN_ID = "can_id"
FEATURE_DLC = "dlc"
FEATURE_DELTA_T = "dt_same_id"
FEATURE_MSG_RATE_50MS = "msg_rate_50ms"
FEATURE_REPETITION_COUNT = "id_repetition_count"
FEATURE_HAMMING_DISTANCE = "hamming_prev_same_id"


@dataclass(frozen=True)
class RuleHit:
    """Represents a triggered deterministic rule evaluation on a CAN frame.

    Attributes:
        rule_id (str): Identifier of the fired rule (e.g. 'R1', 'R2', 'R3', 'R4').
        reason (str): Human-readable diagnostic description of the trigger condition.
        weight (int): Architectural severity weight (1: low, 2: medium, 3: critical).
        verdict (str): Rule verdict ('VIOLATION' for hard protocol breaks, 'SUSPECT' for heuristics).
    """

    rule_id: str
    reason: str
    weight: int
    verdict: str = ""

    def __post_init__(self) -> None:
        if not self.verdict:
            # Fixed architectural mapping: weight 3 -> VIOLATION, weight 1-2 -> SUSPECT
            v = "VIOLATION" if self.weight >= 3 else "SUSPECT"
            object.__setattr__(self, "verdict", v)


def _extract_frame_attributes(f: Any) -> Tuple[int, int]:
    """Extract (can_id, dlc) as integers from a CAN frame representation."""
    if isinstance(f, dict):
        raw_id = f.get(FEATURE_CAN_ID, f.get("CAN ID", f.get("id", 0)))
        raw_dlc = f.get(FEATURE_DLC, f.get("DLC", 8))
    else:
        raw_id = getattr(f, FEATURE_CAN_ID, getattr(f, "CAN ID", getattr(f, "id", 0)))
        raw_dlc = getattr(f, FEATURE_DLC, getattr(f, "DLC", 8))

    if isinstance(raw_id, str):
        v = raw_id.strip()
        if v.lower().startswith("0x"):
            can_id = int(v, 16)
        else:
            try:
                can_id = int(v)
            except ValueError:
                can_id = int(v, 16)
    else:
        can_id = int(raw_id)

    dlc = int(raw_dlc)
    return can_id, dlc


def _extract_feature(f: Any, primary_name: str, aliases: List[str]) -> Optional[float]:
    """Extract a numeric feature from frame using primary name and aliases."""
    candidate_names = [primary_name] + [a for a in aliases if a != primary_name]
    for name in candidate_names:
        if isinstance(f, dict):
            if name in f and f[name] is not None:
                return float(f[name])
        else:
            val = getattr(f, name, None)
            if val is not None:
                return float(val)
    return None


def r1_unknown_id(
    f: Any,
    bp: Optional[Any] = None,
    cfg: Optional[Any] = None,
) -> Optional[RuleHit]:
    """Rule 1 (R1): Check for unauthorized / unknown CAN arbitration ID.

    Fires when the frame's CAN ID is not present in the authorized baseline
    whitelist (indicated by bp is None or can_id not in whitelist).

    Args:
        f: CAN frame representation (CANFrameInput, dict, or object with can_id).
        bp: Per-ID baseline profile (None if ID is unseen/unauthorized) or BaselineProfiler.
        cfg: Optional rule configuration dictionary or object.

    Returns:
        RuleHit with weight 3 and verdict VIOLATION if unauthorized, else None.
    """
    can_id, _ = _extract_frame_attributes(f)

    # 1. If bp is None, frame ID is not in the whitelist / has no profile
    if bp is None:
        reason = "unknown CAN ID 0x%03X" % can_id
        return RuleHit(rule_id="R1", reason=reason, weight=3, verdict="VIOLATION")

    # 2. If bp is BaselineProfiler or object with id_whitelist
    if hasattr(bp, "id_whitelist"):
        whitelist = bp.id_whitelist
        if can_id not in whitelist:
            reason = "unknown CAN ID 0x%03X" % can_id
            return RuleHit(rule_id="R1", reason=reason, weight=3, verdict="VIOLATION")

    # 3. If bp is a collection/dict
    elif isinstance(bp, (set, list, tuple)):
        if can_id not in bp:
            reason = "unknown CAN ID 0x%03X" % can_id
            return RuleHit(rule_id="R1", reason=reason, weight=3, verdict="VIOLATION")

    # 4. If cfg provides an explicit whitelist
    if cfg is not None:
        whitelist = getattr(cfg, "id_whitelist", None)
        if whitelist is None and isinstance(cfg, dict):
            whitelist = cfg.get("id_whitelist")
            if whitelist is None:
                whitelist = cfg.get("per_id_baselines", {}).get("id_whitelist")
        if whitelist is not None and can_id not in whitelist:
            reason = "unknown CAN ID 0x%03X" % can_id
            return RuleHit(rule_id="R1", reason=reason, weight=3, verdict="VIOLATION")

    return None


def r2_impossible_dt(
    f: Any,
    bp: Optional[Any] = None,
    cfg: Optional[Any] = None,
) -> Optional[RuleHit]:
    """Rule 2 (R2): Check for impossible inter-arrival time.

    Fires when elapsed time since the previous frame of the same CAN ID is
    below the learned floor: dt_same_id < bp.p01_dt * cfg.r2_factor.

    Args:
        f: CAN frame representation (must contain dt_same_id / delta_t).
        bp: Per-ID baseline profile (containing p01_dt) or BaselineProfiler.
        cfg: Rule configuration (containing r2_factor).

    Returns:
        RuleHit with weight 3 and verdict VIOLATION if below learned floor, else None.
    """
    if bp is None:
        return None

    dt_same_id = _extract_feature(f, FEATURE_DELTA_T, ["dt_same_id", "delta_t", "dt"])
    if dt_same_id is None:
        return None

    can_id, _ = _extract_frame_attributes(f)

    # Extract p01_dt
    p01_dt = None
    if hasattr(bp, "p01_dt"):
        modal_obj = bp.p01_dt
        if isinstance(modal_obj, (int, float)):
            p01_dt = float(modal_obj)
        elif hasattr(modal_obj, "get"):
            p01_dt = modal_obj.get(can_id)
    elif isinstance(bp, dict):
        if "p01_dt" in bp:
            val = bp["p01_dt"]
            p01_dt = (
                val.get(can_id)
                if isinstance(val, dict)
                else float(val) if val is not None else None
            )
        elif can_id in bp:
            p01_dt = float(bp[can_id])
    elif isinstance(bp, (int, float)):
        p01_dt = float(bp)

    if p01_dt is None or p01_dt <= 0:
        return None

    # Extract r2_factor and physical_min_dt
    r2_factor = 0.5
    physical_min = 0.00020
    if cfg is not None:
        factor_val = getattr(cfg, "r2_factor", None)
        if factor_val is None and isinstance(cfg, dict):
            factor_val = cfg.get("r2_factor")
            if factor_val is None:
                factor_val = cfg.get("global_tuned_thresholds", {}).get("r2_factor")
        if factor_val is not None:
            r2_factor = float(factor_val)

        pmin_val = getattr(cfg, "physical_min_dt", None)
        if pmin_val is None and isinstance(cfg, dict):
            pmin_val = cfg.get("physical_min_dt")
            if pmin_val is None:
                pmin_val = cfg.get("global_tuned_thresholds", {}).get("physical_min_dt")
        if pmin_val is not None:
            physical_min = float(pmin_val)

    learned_floor = max(physical_min, p01_dt * r2_factor)

    if dt_same_id < learned_floor:
        x_ms = dt_same_id * 1000.0
        y_ms = learned_floor * 1000.0
        reason = f"Δt={x_ms:.1f}ms below learned floor {y_ms:.1f}ms"
        return RuleHit(rule_id="R2", reason=reason, weight=3, verdict="VIOLATION")

    return None


def r3_flooding(
    f: Any,
    bp: Optional[Any] = None,
    cfg: Optional[Any] = None,
) -> Optional[RuleHit]:
    """Rule 3 (R3): Check for global bus message flooding / frequency exceeded.

    Fires when aggregate bus rate in trailing 50ms window exceeds global threshold:
    msg_rate_50ms > cfg.r3_global_rate. Operates independently of bp.

    Args:
        f: CAN frame representation (must contain msg_rate_50ms).
        bp: Per-ID profile (unused, can be None).
        cfg: Rule configuration (containing r3_global_rate).

    Returns:
        RuleHit with weight 3 and verdict VIOLATION if flooding detected, else None.
    """
    msg_rate = _extract_feature(
        f,
        FEATURE_MSG_RATE_50MS,
        ["msg_rate_50ms", "msg_count_50ms", "bus_rate"],
    )
    if msg_rate is None:
        return None

    r3_limit = 15.0
    if cfg is not None:
        limit_val = getattr(cfg, "r3_global_rate", None)
        if limit_val is None and isinstance(cfg, dict):
            limit_val = cfg.get("r3_global_rate")
            if limit_val is None:
                limit_val = cfg.get("global_tuned_thresholds", {}).get("r3_global_rate")
        if limit_val is not None:
            r3_limit = float(limit_val)

    if msg_rate > r3_limit:
        x_str = (
            str(int(msg_rate)) if float(msg_rate).is_integer() else f"{msg_rate:.1f}"
        )
        y_str = (
            str(int(r3_limit)) if float(r3_limit).is_integer() else f"{r3_limit:.1f}"
        )
        reason = f"bus rate {x_str} msgs/50ms exceeds {y_str}"
        return RuleHit(rule_id="R3", reason=reason, weight=3, verdict="VIOLATION")

    return None


def r4_dlc(
    f: Any,
    bp: Optional[Any] = None,
    cfg: Optional[Any] = None,
) -> Optional[RuleHit]:
    """Rule 4 (R4): Check Data Length Code (DLC) compliance.

    Fires when DLC is outside the CAN 2.0B physical domain bounds [0, 8]
    or deviates from the expected modal DLC for this CAN ID.

    Args:
        f: CAN frame representation (CANFrameInput, dict, or object with can_id, dlc).
        bp: Per-ID baseline profile (containing modal_dlc) or BaselineProfiler instance.
        cfg: Optional rule configuration dictionary or object.

    Returns:
        RuleHit with weight 2 and verdict SUSPECT if DLC is invalid, else None.
    """
    can_id, dlc = _extract_frame_attributes(f)

    # Determine expected DLC
    expected_dlc = 8
    if bp is not None:
        if hasattr(bp, "modal_dlc"):
            modal = bp.modal_dlc
            if isinstance(modal, int):
                expected_dlc = modal
            elif hasattr(modal, "get"):
                expected_dlc = modal.get(can_id, 8)
        elif isinstance(bp, dict):
            if "modal_dlc" in bp:
                m = bp["modal_dlc"]
                expected_dlc = m.get(can_id, 8) if isinstance(m, dict) else int(m)
            elif can_id in bp:
                expected_dlc = int(bp[can_id])
        elif isinstance(bp, int):
            expected_dlc = bp
    elif cfg is not None:
        expected_dlc = getattr(cfg, "modal_dlc_default", None)
        if expected_dlc is None and isinstance(cfg, dict):
            expected_dlc = cfg.get("modal_dlc_default")
            if expected_dlc is None:
                expected_dlc = cfg.get("global_tuned_thresholds", {}).get(
                    "modal_dlc_default", 8
                )
        if expected_dlc is None:
            expected_dlc = 8

    # Trigger condition: dlc outside physical [0, 8] bounds OR dlc != expected_dlc
    if not (0 <= dlc <= 8) or (dlc != expected_dlc):
        reason = f"DLC {dlc} != expected {expected_dlc} for 0x{can_id:03X}"
        return RuleHit(rule_id="R4", reason=reason, weight=2, verdict="SUSPECT")

    return None


def r5_repetition(
    f: Any,
    bp: Optional[Any] = None,
    cfg: Optional[Any] = None,
) -> Optional[RuleHit]:
    """Rule 5 (R5): Check for consecutive identical payload repetition bursts.

    Fires when consecutive identical payloads for this CAN ID exceed the
    normal 99.5th percentile baseline: id_repetition_count > bp.p995_rep.

    Args:
        f: CAN frame representation (must contain id_repetition_count).
        bp: Per-ID baseline profile (containing p995_rep) or BaselineProfiler.
        cfg: Rule configuration (containing default_max_repetition fallback).

    Returns:
        RuleHit with weight 2 and verdict SUSPECT if repetition burst detected, else None.
    """
    if bp is None:
        return None

    rep_count = _extract_feature(
        f,
        FEATURE_REPETITION_COUNT,
        ["id_repetition_count", "repetition_count", "repetition", "rep_count"],
    )
    if rep_count is None:
        return None

    can_id, _ = _extract_frame_attributes(f)

    # Extract p995_rep
    threshold = None
    if hasattr(bp, "p995_rep"):
        val = bp.p995_rep
        if isinstance(val, (int, float)):
            threshold = float(val)
        elif hasattr(val, "get"):
            threshold = val.get(can_id)
    elif isinstance(bp, dict):
        if "p995_rep" in bp:
            val = bp["p995_rep"]
            threshold = (
                val.get(can_id)
                if isinstance(val, dict)
                else float(val) if val is not None else None
            )
        elif can_id in bp:
            threshold = float(bp[can_id])
    elif isinstance(bp, (int, float)):
        threshold = float(bp)

    if threshold is None and cfg is not None:
        fallback = getattr(cfg, "default_max_repetition", None)
        if fallback is None and isinstance(cfg, dict):
            fallback = cfg.get("default_max_repetition")
            if fallback is None:
                fallback = cfg.get("global_tuned_thresholds", {}).get(
                    "default_max_repetition"
                )
        if fallback is not None:
            threshold = float(fallback)

    if threshold is None:
        threshold = 5.0

    if rep_count > threshold:
        n_str = (
            str(int(rep_count)) if float(rep_count).is_integer() else f"{rep_count:.1f}"
        )
        y_str = (
            str(int(threshold)) if float(threshold).is_integer() else f"{threshold:.1f}"
        )
        reason = f"{n_str} repeats in last 50 frames (p99.5={y_str})"
        return RuleHit(rule_id="R5", reason=reason, weight=2, verdict="SUSPECT")

    return None


def r6_payload(
    f: Any,
    bp: Optional[Any] = None,
    cfg: Optional[Any] = None,
) -> Optional[RuleHit]:
    """Rule 6 (R6): Check for abnormal payload rate of change / bitwise jump.

    Fires when the ID is periodic AND the consecutive bitwise Hamming distance
    exceeds the 99th percentile baseline: bp.is_periodic AND hamming_prev_same_id > bp.p99_hamming.

    Args:
        f: CAN frame representation (must contain hamming_prev_same_id).
        bp: Per-ID baseline profile (containing is_periodic, p99_hamming) or BaselineProfiler.
        cfg: Rule configuration (containing default_max_hamming fallback).

    Returns:
        RuleHit with weight 2 and verdict SUSPECT if payload jump detected, else None.
    """
    if bp is None:
        return None

    hamming = _extract_feature(
        f,
        FEATURE_HAMMING_DISTANCE,
        [
            "hamming_prev_same_id",
            "hamming_distance",
            "hamming_prev",
            "hamming",
        ],
    )
    if hamming is None:
        return None

    can_id, _ = _extract_frame_attributes(f)

    # Extract is_periodic
    is_periodic = False
    if hasattr(bp, "is_periodic"):
        val = bp.is_periodic
        if isinstance(val, (bool, int)):
            is_periodic = bool(val)
        elif hasattr(val, "get"):
            is_periodic = bool(val.get(can_id, False))
    elif isinstance(bp, dict):
        if "is_periodic" in bp:
            val = bp["is_periodic"]
            is_periodic = (
                bool(val.get(can_id, False)) if isinstance(val, dict) else bool(val)
            )
        elif can_id in bp:
            is_periodic = bool(bp[can_id])
    elif isinstance(bp, bool):
        is_periodic = bp

    # R6 only applies to periodic ECUs (event-driven IDs have discontinuous payloads)
    if not is_periodic:
        return None

    # Extract p99_hamming
    threshold = None
    if hasattr(bp, "p99_hamming"):
        val = bp.p99_hamming
        if isinstance(val, (int, float)):
            threshold = float(val)
        elif hasattr(val, "get"):
            threshold = val.get(can_id)
    elif isinstance(bp, dict):
        if "p99_hamming" in bp:
            val = bp["p99_hamming"]
            threshold = (
                val.get(can_id)
                if isinstance(val, dict)
                else float(val) if val is not None else None
            )
        elif can_id in bp:
            threshold = float(bp[can_id])
    elif isinstance(bp, (int, float)):
        threshold = float(bp)

    if threshold is None and cfg is not None:
        fallback = getattr(cfg, "default_max_hamming", None)
        if fallback is None and isinstance(cfg, dict):
            fallback = cfg.get("default_max_hamming")
            if fallback is None:
                fallback = cfg.get("global_tuned_thresholds", {}).get(
                    "default_max_hamming"
                )
        if fallback is not None:
            threshold = float(fallback)

    if threshold is None:
        threshold = 48.0

    if hamming > threshold:
        n_str = str(int(hamming)) if float(hamming).is_integer() else f"{hamming:.1f}"
        y_str = (
            str(int(threshold)) if float(threshold).is_integer() else f"{threshold:.1f}"
        )
        reason = f"payload jumped {n_str} bits (p99={y_str})"
        return RuleHit(rule_id="R6", reason=reason, weight=2, verdict="SUSPECT")

    return None


def r7_silence(
    f: Any,
    bp: Optional[Any] = None,
    cfg: Optional[Any] = None,
) -> Optional[RuleHit]:
    """Rule 7 (R7): Check for unexpected message silence / watchdog timeout.

    Fires when the elapsed time since the previous frame of the same CAN ID
    exceeds the watchdog ceiling: dt_same_id > bp.p99_dt * cfg.r7_factor.
    Only applies to periodic ECUs.

    Args:
        f: CAN frame representation (must contain dt_same_id / delta_t).
        bp: Per-ID baseline profile (containing p99_dt, is_periodic) or BaselineProfiler.
        cfg: Rule configuration (containing r7_factor).

    Returns:
        RuleHit with weight 1 and verdict SUSPECT if silence detected, else None.
    """
    if bp is None:
        return None

    dt_same_id = _extract_feature(f, FEATURE_DELTA_T, ["dt_same_id", "delta_t", "dt"])
    if dt_same_id is None:
        return None

    can_id, _ = _extract_frame_attributes(f)

    # Check periodicity â€” R7 only applies to periodic ECUs
    is_periodic = False
    if hasattr(bp, "is_periodic"):
        val = bp.is_periodic
        if isinstance(val, (bool, int)):
            is_periodic = bool(val)
        elif hasattr(val, "get"):
            is_periodic = bool(val.get(can_id, False))
    elif isinstance(bp, dict):
        if "is_periodic" in bp:
            val = bp["is_periodic"]
            is_periodic = (
                bool(val.get(can_id, False)) if isinstance(val, dict) else bool(val)
            )
    elif isinstance(bp, bool):
        is_periodic = bp

    if not is_periodic:
        return None

    # Extract p99_dt
    p99_dt = None
    if hasattr(bp, "p99_dt"):
        val = bp.p99_dt
        if isinstance(val, (int, float)):
            p99_dt = float(val)
        elif hasattr(val, "get"):
            p99_dt = val.get(can_id)
    elif isinstance(bp, dict):
        if "p99_dt" in bp:
            val = bp["p99_dt"]
            p99_dt = (
                val.get(can_id)
                if isinstance(val, dict)
                else float(val) if val is not None else None
            )
        elif can_id in bp:
            p99_dt = float(bp[can_id])
    elif isinstance(bp, (int, float)):
        p99_dt = float(bp)

    if p99_dt is None or p99_dt <= 0:
        return None

    # Extract r7_factor
    r7_factor = 5.0
    if cfg is not None:
        factor_val = getattr(cfg, "r7_factor", None)
        if factor_val is None and isinstance(cfg, dict):
            factor_val = cfg.get("r7_factor")
            if factor_val is None:
                factor_val = cfg.get("global_tuned_thresholds", {}).get("r7_factor")
        if factor_val is not None:
            r7_factor = float(factor_val)

    timeout = p99_dt * r7_factor

    if dt_same_id > timeout:
        x_ms = dt_same_id * 1000.0
        reason = f"expected message missing for {x_ms:.1f}ms"
        return RuleHit(rule_id="R7", reason=reason, weight=1, verdict="SUSPECT")

    return None


def check_silence_timeouts(
    last_seen_dict: dict[int, float],
    current_timestamp: float,
    bp: Optional[Any] = None,
    cfg: Optional[Any] = None,
) -> list[RuleHit]:
    """Time-based silence watchdog check for periodic ECUs.

    Evaluates whether any known periodic CAN ID has stopped transmitting
    based on elapsed time since its last observed frame, even when no new
    frame has arrived for that ID.

    Args:
        last_seen_dict: Mapping of CAN ID -> float timestamp of last seen frame.
        current_timestamp: Current bus virtual timestamp or wall-clock epoch.
        bp: BaselineProfiler or baseline dict containing is_periodic and p99_dt.
        cfg: Rule configuration (containing r7_factor).

    Returns:
        List of RuleHit instances for timed-out periodic IDs.
    """
    if bp is None:
        return []

    r7_factor = 4.0
    if cfg is not None:
        factor_val = getattr(cfg, "r7_factor", None)
        if factor_val is None and isinstance(cfg, dict):
            factor_val = cfg.get("r7_factor")
            if factor_val is None:
                factor_val = cfg.get("global_tuned_thresholds", {}).get("r7_factor")
        if factor_val is not None:
            r7_factor = float(factor_val)

    periodic_map = getattr(bp, "is_periodic", {})
    p99_map = getattr(bp, "p99_dt", {})

    hits: list[RuleHit] = []
    for can_id, last_ts in last_seen_dict.items():
        is_periodic = False
        if hasattr(periodic_map, "get"):
            is_periodic = bool(periodic_map.get(can_id, False))
        elif isinstance(periodic_map, dict):
            is_periodic = bool(periodic_map.get(can_id, False))

        if not is_periodic:
            continue

        p99_dt = None
        if hasattr(p99_map, "get"):
            p99_dt = p99_map.get(can_id)
        elif isinstance(p99_map, dict):
            p99_dt = p99_map.get(can_id)

        if p99_dt is None or p99_dt <= 0:
            continue

        timeout = p99_dt * r7_factor
        elapsed = current_timestamp - last_ts
        if elapsed > timeout:
            x_ms = elapsed * 1000.0
            t_ms = timeout * 1000.0
            reason = f"watchdog timeout for 0x{can_id:03X}: elapsed {x_ms:.1f}ms exceeds {t_ms:.1f}ms"
            hits.append(RuleHit(rule_id="R7", reason=reason, weight=1, verdict="SUSPECT"))

    return hits


# Ordered list of all 7 Stage 1 rule functions for RuleEngine iteration.
# Maintained in rule priority order: R1, R2, R3 (VIOLATION) then R4-R7 (SUSPECT).
RULES = [
    r1_unknown_id,
    r2_impossible_dt,
    r3_flooding,
    r4_dlc,
    r5_repetition,
    r6_payload,
    r7_silence,
]
