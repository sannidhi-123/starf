"""Severity scoring engine for STARF hybrid decisions.

Computes operational severity points (0-12) and maps to actionable incident response tiers.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple


def score(
    decision: Any,
    rule_verdict: Any,
    can_id: Optional[Any] = None,
) -> Tuple[int, str]:
    """Calculate severity score (0-12) and categorical level.

    Formula:
        base:
            - 'dos', 'fuzzy', 'spoofing': 3
            - 'ATTACK (unclassified)': 3
            - 'SUSPICIOUS': 1
            - 'normal': 0
        + min(3, rule_verdict.score)
        + confidence (>=0.9: 2, >=0.7: 1, else 0)
        + persistence (3 if stage == 'stage1_persistent', else 0)

    Levels:
        - score >= 9: 'CRITICAL'
        - score 6-8:  'HIGH'
        - score 3-5:  'MEDIUM'
        - score 1-2:  'LOW'
        - score 0:    'NONE'

    If decision.severity_cap == 'MEDIUM', clamp to at most 'MEDIUM'.

    Args:
        decision: Decision dataclass or object with label, confidence, stage, and severity_cap.
        rule_verdict: RuleVerdict object with score attribute.
        can_id: Optional CAN arbitration ID.

    Returns:
        Tuple of (score: int in 0-12, level: str).
    """
    # 1. Base score from decision label
    label_norm = str(getattr(decision, "label", "")).strip()
    label_lower = label_norm.lower()

    if label_lower in ("dos", "fuzzy", "spoofing"):
        base = 3
    elif label_lower == "attack (unclassified)":
        base = 3
    elif label_lower == "suspicious":
        base = 1
    elif label_lower == "normal":
        base = 0
    else:
        # Default fallback for unlisted anomaly types
        base = 3 if label_lower != "normal" else 0

    # 2. Stage 1 rule score term
    rule_score = getattr(rule_verdict, "score", 0) if rule_verdict is not None else 0
    rule_pts = min(3, max(0, int(rule_score)))

    # 3. Confidence term
    conf = float(getattr(decision, "confidence", 0.0))
    if conf >= 0.90:
        conf_pts = 2
    elif conf >= 0.70:
        conf_pts = 1
    else:
        conf_pts = 0

    # 4. Persistence term
    stage = getattr(decision, "stage", "")
    persistence_pts = 3 if stage == "stage1_persistent" else 0

    # Aggregate numerical score (0-12)
    total_score = base + rule_pts + conf_pts + persistence_pts
    total_score = max(0, min(12, total_score))

    # Categorical severity level
    if total_score >= 9:
        level = "CRITICAL"
    elif total_score >= 6:
        level = "HIGH"
    elif total_score >= 3:
        level = "MEDIUM"
    elif total_score >= 1:
        level = "LOW"
    else:
        level = "NONE"

    # Clamp level if severity_cap is MEDIUM
    severity_cap = getattr(decision, "severity_cap", None)
    if severity_cap == "MEDIUM":
        if level in ("CRITICAL", "HIGH"):
            level = "MEDIUM"

    return total_score, level
