"""Stage 1 deterministic rule definitions for CAN-Bus anomaly detection.

Implements protocol rules R1 (unknown CAN ID) and R4 (DLC compliance violation)
according to docs/rule_spec.md and config/rules.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple


@dataclass(frozen=True)
class RuleHit:
    """Represents a triggered deterministic rule evaluation on a CAN frame.

    Attributes:
        rule_id (str): Identifier of the fired rule (e.g. 'R1', 'R4').
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
    """Extract (can_id, dlc) as integers from a CAN frame representation.

    Supports dicts, Pydantic models (e.g. CANFrameInput), or attribute-based objects.
    """
    if isinstance(f, dict):
        raw_id = f.get("can_id", f.get("CAN ID", f.get("id", 0)))
        raw_dlc = f.get("dlc", f.get("DLC", 8))
    else:
        raw_id = getattr(f, "can_id", getattr(f, "CAN ID", getattr(f, "id", 0)))
        raw_dlc = getattr(f, "dlc", getattr(f, "DLC", 8))

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
