"""Stage 1 Rule Engine for STARK CAN-Bus anomaly detection.

Applies all seven deterministic rules to each incoming CAN frame and
produces a composite verdict: VIOLATION, SUSPECT, or CLEAN.

Usage::

    engine = RuleEngine.from_yaml("config/rules.yaml", profiler)
    verdict = engine.evaluate(frame)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional, Union

import yaml

from stark.rules.definitions import RULES, RuleHit
from stark.utils.exceptions import RuleConfigError


@dataclass(frozen=True)
class RuleVerdict:
    """Composite result of evaluating all Stage 1 rules against a single CAN frame.

    Attributes:
        verdict (str): Aggregate verdict: 'VIOLATION', 'SUSPECT', or 'CLEAN'.
        score (int): Sum of weights of all fired rules.
        hits (List[RuleHit]): Ordered list of rule hits (fired rules only).
    """

    verdict: str
    score: int
    hits: List[RuleHit] = field(default_factory=list)


class RuleEngine:
    """Stage 1 deterministic rule evaluation engine.

    Applies all rules in the RULES list to each frame, aggregates weights,
    and produces a composite RuleVerdict.

    Verdict arbitration (docs/rule_spec.md §2.2):
        - VIOLATION  if any fired rule has weight >= 3 (R1, R2, R3)
        - SUSPECT    elif total score >= 2 (any weight-2 rule, or multiple weight-1)
        - CLEAN      otherwise (score <= 1 with no weight-3 hits)

    Args:
        cfg: Parsed configuration dict from rules.yaml.
        profile: Fitted BaselineProfiler instance.
        rules: List of rule callables (defaults to all 7 from definitions.RULES).
    """

    def __init__(
        self,
        cfg: dict,
        profile: Optional[Any] = None,
        rules: Optional[List[Callable]] = None,
    ) -> None:
        self._cfg = cfg
        self._profile = profile
        self._rules: List[Callable] = rules if rules is not None else RULES

    @classmethod
    def from_yaml(
        cls,
        rules_yaml: Union[str, Path],
        profile: Optional[Any] = None,
        rules: Optional[List[Callable]] = None,
    ) -> RuleEngine:
        """Construct RuleEngine by loading and validating a rules.yaml file.

        Args:
            rules_yaml: Path to the rules.yaml configuration file.
            profile: Fitted BaselineProfiler instance.
            rules: Optional override of the rule callable list.

        Returns:
            Configured RuleEngine instance.

        Raises:
            RuleConfigError: If the file is missing, unreadable, or malformed.
        """
        path = Path(rules_yaml)
        if not path.exists():
            raise RuleConfigError(f"rules.yaml not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise RuleConfigError(f"rules.yaml is not valid YAML: {exc}") from exc

        if not isinstance(cfg, dict):
            raise RuleConfigError(
                f"rules.yaml must be a YAML mapping, got {type(cfg).__name__}"
            )

        required_keys = {"global_tuned_thresholds", "per_id_baselines"}
        missing = required_keys - cfg.keys()
        if missing:
            raise RuleConfigError(
                f"rules.yaml is missing required top-level keys: {missing}"
            )

        return cls(cfg=cfg, profile=profile, rules=rules)

    def _get_per_id_profile(self, can_id: int) -> Optional[Any]:
        """Return per-ID baseline profile object for a given CAN ID.

        Looks up the CAN ID in the BaselineProfiler's id_whitelist.
        Returns None if the ID is not in the whitelist (triggers R1).
        """
        if self._profile is None:
            return None

        whitelist = getattr(self._profile, "id_whitelist", [])
        if can_id not in whitelist:
            return None  # Unknown ID — R1 will fire

        return self._profile  # Pass the full profiler; rules extract fields by can_id

    def _extract_can_id(self, f: Any) -> int:
        """Extract canonical integer CAN ID from a frame."""
        if isinstance(f, dict):
            raw = f.get("can_id", f.get("CAN ID", f.get("id", 0)))
        else:
            raw = getattr(f, "can_id", getattr(f, "id", 0))

        if isinstance(raw, str):
            v = raw.strip()
            if v.lower().startswith("0x"):
                return int(v, 16)
            try:
                return int(v)
            except ValueError:
                return int(v, 16)
        return int(raw)

    def evaluate(self, f: Any) -> RuleVerdict:
        """Evaluate all Stage 1 rules against a single CAN frame.

        Args:
            f: CAN frame representation (CANFrameInput, dict, or attribute-based object).

        Returns:
            RuleVerdict with composite verdict, score, and list of hits.
        """
        can_id = self._extract_can_id(f)
        bp = self._get_per_id_profile(can_id)

        hits: List[RuleHit] = []
        for rule_fn in self._rules:
            hit = rule_fn(f, bp, self._cfg)
            if hit is not None:
                hits.append(hit)

        score = sum(h.weight for h in hits)

        if any(h.weight >= 3 for h in hits):
            verdict = "VIOLATION"
        elif score >= 2:
            verdict = "SUSPECT"
        else:
            verdict = "CLEAN"

        return RuleVerdict(verdict=verdict, score=score, hits=hits)
