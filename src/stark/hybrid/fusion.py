"""Hybrid Fusion arbitration module.

Arbitrates between Stage 1 deterministic rule engine verdicts and Stage 2 ML predictions
using a strict 7-row priority table.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Probability thresholds for arbitration
TAU_HI: float = 0.85
TAU_LO: float = 0.50
TAU_CLEAN_SAMPLE: float = 0.90


@dataclass
class Decision:
    """Arbitration decision output by hybrid fusion.

    Attributes:
        label: Final attributed classification label (e.g. 'normal', 'dos', 'fuzzy',
            'spoofing', 'ATTACK (unclassified)', 'SUSPICIOUS').
        confidence: Decision confidence score in [0.0, 1.0].
        stage: Pipeline stage responsible ('both' | 'stage1' | 'stage2' | 'stage1_persistent').
        severity_cap: Optional severity ceiling (None | 'MEDIUM').
        rule_ids: List of fired Stage 1 rule IDs.
        reason: Human-readable diagnostic rationale string.
    """

    label: str
    confidence: float
    stage: str
    severity_cap: Optional[str] = None
    rule_ids: List[str] = field(default_factory=list)
    reason: str = ""


class FusionState:
    """Per-CAN-ID sliding window tracker of SUSPECT verdict timestamps (no globals)."""

    def __init__(self, window_sec: float = 1.0) -> None:
        self.window_sec: float = window_sec
        self.suspect_timestamps: Dict[int, collections.deque[float]] = (
            collections.defaultdict(collections.deque)
        )

    def record_suspect(self, can_id: int, timestamp: float) -> int:
        """Record timestamp of a SUSPECT verdict on can_id and return count within window."""
        dq = self.suspect_timestamps[can_id]
        ts = float(timestamp)
        dq.append(ts)
        cutoff = ts - self.window_sec
        while dq and dq[0] < cutoff:
            dq.popleft()
        return len(dq)

    def clear(self) -> None:
        """Clear all stored per-ID timestamp queues."""
        self.suspect_timestamps.clear()


def _normalize_can_id(cid: Any) -> Optional[int]:
    """Convert CAN ID representation to integer if possible."""
    if cid is None:
        return None
    if isinstance(cid, int):
        return cid
    if isinstance(cid, str):
        s = cid.strip()
        try:
            if s.lower().startswith("0x"):
                return int(s, 16)
            return int(s)
        except ValueError:
            try:
                return int(s, 16)
            except ValueError:
                return None
    try:
        return int(cid)
    except (ValueError, TypeError):
        return None


def _extract_rule_ids(rule_verdict: Any) -> List[str]:
    """Extract list of fired rule IDs from a RuleVerdict object."""
    if rule_verdict is None:
        return []
    if hasattr(rule_verdict, "hits") and rule_verdict.hits:
        return [getattr(h, "rule_id", str(h)) for h in rule_verdict.hits]
    if hasattr(rule_verdict, "rule_ids") and rule_verdict.rule_ids:
        return list(rule_verdict.rule_ids)
    return []


def decide(
    rule_verdict: Any,
    stage2_class: str,
    stage2_prob: float,
    can_id: Optional[Any] = None,
    timestamp: Optional[float] = None,
    state: Optional[FusionState] = None,
    sampled: bool = False,
) -> Decision:
    """Arbitrate between Stage 1 RuleVerdict and Stage 2 ML prediction.

    Evaluates in strict priority order (7 rows):
    1. VIOLATION and class != normal -> label=class, conf=0.5+0.5*p, stage 'both'
    2. VIOLATION and class == normal -> label 'ATTACK (unclassified)', conf 0.70, stage 'stage1'
    3. SUSPECT and class != normal and p >= 0.85 -> label=class, conf=p, stage 'both'
    4. SUSPECT and class != normal and 0.50 <= p < 0.85 -> label=class, conf=p, stage 'stage2', severity_cap 'MEDIUM'
    5. SUSPECT and (class == normal or p < 0.50) -> 'normal', unless >= 3 SUSPECT on the same ID
       within 1 second (including this one) -> 'SUSPICIOUS', conf 0.40, stage 'stage1_persistent'
    6. CLEAN and sampled and class != normal and p >= 0.90 -> label=class, conf=p, stage 'stage2'
    7. CLEAN otherwise -> 'normal', conf 1.0, stage 'stage1'

    Args:
        rule_verdict: stark.rules.engine.RuleVerdict (verdict, score, hits).
        stage2_class: Predicted class string from Stage 2 ('normal', 'dos', 'fuzzy', 'spoofing', etc.).
        stage2_prob: Stage 2 class probability / confidence in [0.0, 1.0].
        can_id: Optional CAN arbitration ID.
        timestamp: Optional epoch or relative timestamp in seconds.
        state: Optional FusionState instance tracking multi-frame history.
        sampled: Whether this frame was sent to Stage 2 via background sampling.

    Returns:
        Decision instance with arbitration result.
    """
    verdict = (
        getattr(rule_verdict, "verdict", "").upper()
        if rule_verdict is not None
        else "CLEAN"
    )
    cls = str(stage2_class).lower() if stage2_class is not None else "normal"
    p = float(stage2_prob)
    rule_ids = _extract_rule_ids(rule_verdict)

    norm_can_id = _normalize_can_id(can_id)
    norm_ts = float(timestamp) if timestamp is not None else None

    # Track state for SUSPECT verdicts
    suspect_count = 0
    if (
        verdict == "SUSPECT"
        and state is not None
        and norm_can_id is not None
        and norm_ts is not None
    ):
        suspect_count = state.record_suspect(norm_can_id, norm_ts)

    # 1. VIOLATION and class != normal -> label=class, conf=0.5+0.5*p, stage "both"
    if verdict == "VIOLATION" and cls != "normal":
        return Decision(
            label=cls,
            confidence=0.5 + 0.5 * p,
            stage="both",
            severity_cap=None,
            rule_ids=rule_ids,
            reason=f"Dual confirmation: Stage 1 VIOLATION confirmed by Stage 2 {cls} (p={p:.2f})",
        )

    # 2. VIOLATION and class == normal -> label "ATTACK (unclassified)", conf 0.70, stage "stage1"
    if verdict == "VIOLATION" and cls == "normal":
        return Decision(
            label="ATTACK (unclassified)",
            confidence=0.70,
            stage="stage1",
            severity_cap=None,
            rule_ids=rule_ids,
            reason="Rule override: Stage 1 VIOLATION with Stage 2 normal classification",
        )

    # 3. SUSPECT and class != normal and p >= 0.85 -> label=class, conf=p, "both"
    if verdict == "SUSPECT" and cls != "normal" and p >= TAU_HI:
        return Decision(
            label=cls,
            confidence=p,
            stage="both",
            severity_cap=None,
            rule_ids=rule_ids,
            reason=f"Dual confirmation: Stage 1 SUSPECT confirmed by Stage 2 {cls} (p={p:.2f} >= {TAU_HI})",
        )

    # 4. SUSPECT and class != normal and 0.50 <= p < 0.85 -> label=class, conf=p, "stage2", severity_cap "MEDIUM"
    if verdict == "SUSPECT" and cls != "normal" and TAU_LO <= p < TAU_HI:
        return Decision(
            label=cls,
            confidence=p,
            stage="stage2",
            severity_cap="MEDIUM",
            rule_ids=rule_ids,
            reason=(
                f"Stage 2 moderate confidence: {cls} (p={p:.2f}) with Stage 1 SUSPECT "
                f"capped at MEDIUM"
            ),
        )

    # 5. SUSPECT and (class == normal or p < 0.50) -> "normal", unless >= 3 SUSPECT on the same ID
    #    within 1 second (including this one) -> "SUSPICIOUS", conf 0.40, "stage1_persistent"
    if verdict == "SUSPECT" and (cls == "normal" or p < TAU_LO):
        if suspect_count >= 3:
            return Decision(
                label="SUSPICIOUS",
                confidence=0.40,
                stage="stage1_persistent",
                severity_cap=None,
                rule_ids=rule_ids,
                reason=(
                    f"Stage 1 persistent suspect: {suspect_count} SUSPECT verdicts within "
                    f"{state.window_sec if state else 1.0}s on CAN ID "
                    f"{hex(norm_can_id) if norm_can_id is not None else 'unknown'}"
                ),
            )
        else:
            return Decision(
                label="normal",
                confidence=p if cls == "normal" else (1.0 - p),
                stage="stage2",
                severity_cap=None,
                rule_ids=rule_ids,
                reason=f"Stage 1 SUSPECT filtered out by Stage 2 {cls} (p={p:.2f})",
            )

    # 6. CLEAN and sampled and class != normal and p >= 0.90 -> label=class, conf=p, "stage2"
    if verdict == "CLEAN" and sampled and cls != "normal" and p >= TAU_CLEAN_SAMPLE:
        return Decision(
            label=cls,
            confidence=p,
            stage="stage2",
            severity_cap=None,
            rule_ids=rule_ids,
            reason=(
                f"Sampled inspection detection: Stage 2 {cls} "
                f"(p={p:.2f} >= {TAU_CLEAN_SAMPLE}) on CLEAN frame"
            ),
        )

    # 7. CLEAN otherwise -> "normal", conf 1.0, "stage1"
    return Decision(
        label="normal",
        confidence=1.0,
        stage="stage1",
        severity_cap=None,
        rule_ids=rule_ids,
        reason="Baseline pass-through: frame is CLEAN",
    )
