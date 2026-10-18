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

    # Extract r2_factor
    r2_factor = 0.5
    if cfg is not None:
        factor_val = getattr(cfg, "r2_factor", None)
        if factor_val is None and isinstance(cfg, dict):
            factor_val = cfg.get("r2_factor")
            if factor_val is None:
                factor_val = cfg.get("global_tuned_thresholds", {}).get("r2_factor")
        if factor_val is not None:
            r2_factor = float(factor_val)

    learned_floor = p01_dt * r2_factor

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
