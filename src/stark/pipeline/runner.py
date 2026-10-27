"""End-to-end detection pipeline.

CAN frames → StreamingFeatures → Stage 1 RuleEngine → Stage 2 stub ML
  → Hybrid Fusion → Severity → alert dicts.

Uses the same ``rebuild_stage1_engine`` logic as ``scripts/eval_stage1_only.py``
(logic is inlined; no import from scripts/).
"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from stark.baseline.profiler import BaselineProfiler
from stark.hybrid.fusion import FusionState, decide
from stark.hybrid.severity import score as severity_score
from stark.ml.predict import Stage2Model
from stark.pipeline.features import StreamingFeatures
from stark.rules.engine import RuleEngine

# Fraction of CLEAN frames forwarded to Stage 2 (deterministic sampling)
_SAMPLE_RATE: float = 0.10
_SAMPLE_SEED: int = 42

# ---------------------------------------------------------------------------
# Helpers (inlined from eval_stage1_only.py — no scripts/ import)
# ---------------------------------------------------------------------------


def _resolve_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols = {str(c).lower().strip(): c for c in df.columns}
    for c in candidates:
        if c.lower().strip() in cols:
            return cols[c.lower().strip()]
    return None


def _filter_normal(df: pd.DataFrame) -> pd.DataFrame:
    flag_col = _resolve_column(
        df, ["flag", "label", "status", "attack", "is_attack", "class"]
    )
    if flag_col is None:
        return df.copy()
    unique = set(df[flag_col].dropna().unique())
    if "R" in unique:
        return df[df[flag_col] == "R"].copy()
    if "normal" in unique:
        return df[df[flag_col] == "normal"].copy()
    if 0 in unique:
        return df[df[flag_col] == 0].copy()
    return df.copy()


def _50ms_p999(df: pd.DataFrame, time_col: str) -> float:
    import numpy as np

    ts = df[time_col].sort_values().values
    if len(ts) == 0:
        return 0.0
    left = np.searchsorted(ts, ts - 0.050, side="left")
    counts = np.arange(len(ts)) - left + 1
    return float(np.percentile(counts, 99.9))


def _build_engine_from_df(
    train_df: pd.DataFrame,
    rules_yaml_path: Optional[Path],
) -> tuple[RuleEngine, BaselineProfiler]:
    """Fit profiler and assemble RuleEngine from normal training frames."""
    normal_df = _filter_normal(train_df)
    if normal_df.empty:
        raise ValueError("No normal training frames found to fit BaselineProfiler.")

    profiler = BaselineProfiler()
    profiler.fit(normal_df)

    time_col = _resolve_column(normal_df, ["timestamp", "time", "ts"])
    assert time_col is not None, "No timestamp column found in training data."
    r3_rate = _50ms_p999(normal_df, time_col)

    cfg: Dict[str, Any] = {}
    if rules_yaml_path is not None and Path(rules_yaml_path).exists():
        with open(rules_yaml_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                cfg = loaded

    cfg.setdefault("global_tuned_thresholds", {})
    thr = cfg["global_tuned_thresholds"]
    thr.setdefault("r2_factor", 0.5)
    thr["r3_global_rate"] = r3_rate
    thr.setdefault("r7_factor", 5.0)
    thr.setdefault("physical_min_dt", 0.00020)
    thr.setdefault("modal_dlc_default", 8)
    thr.setdefault("default_max_repetition", 5)
    thr.setdefault("default_max_hamming", 48)

    cfg.setdefault("per_id_baselines", {})
    pib = cfg["per_id_baselines"]
    pib["id_whitelist"] = [int(i) for i in profiler.id_whitelist]
    pib["modal_dlc"] = {int(k): int(v) for k, v in profiler.modal_dlc.items()}
    pib["p01_dt"] = {int(k): float(v) for k, v in profiler.p01_dt.items()}
    pib["p99_dt"] = {int(k): float(v) for k, v in profiler.p99_dt.items()}
    pib["p995_rep"] = {int(k): float(v) for k, v in profiler.p995_rep.items()}
    pib["p99_hamming"] = {int(k): float(v) for k, v in profiler.p99_hamming.items()}
    pib["is_periodic"] = {int(k): bool(v) for k, v in profiler.is_periodic.items()}

    engine = RuleEngine(cfg=cfg, profile=profiler)
    return engine, profiler


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------


class DetectionPipeline:
    """End-to-end CAN-frame anomaly detection pipeline.

    Instantiate once (expensive: fits profiler), then call :meth:`run` for each
    batch of frames.
    """

    def __init__(
        self,
        engine: RuleEngine,
        stage2: Stage2Model,
        rng: random.Random,
    ) -> None:
        self._engine = engine
        self._stage2 = stage2
        self._rng = rng

    @classmethod
    def from_config(
        cls,
        rules_yaml: str = "config/rules.yaml",
        baseline_csv: str = "data/samples/fixture.csv",
    ) -> "DetectionPipeline":
        """Factory: load baseline CSV, fit profiler, build RuleEngine + Stage2Model.

        Args:
            rules_yaml: Path to the YAML rule configuration file.
            baseline_csv: Path to the baseline normal-traffic CSV used to fit
                          the BaselineProfiler (Car-Hacking format).
        """
        rules_path = Path(rules_yaml)
        if not rules_path.is_file():
            for parent in [Path.cwd()] + list(Path.cwd().parents):
                candidate = parent / rules_yaml
                if candidate.is_file():
                    rules_path = candidate
                    break

        csv_path = Path(baseline_csv)
        if not csv_path.is_file():
            for parent in [Path.cwd()] + list(Path.cwd().parents):
                candidate = parent / baseline_csv
                if candidate.is_file():
                    csv_path = candidate
                    break

        if not csv_path.exists():
            raise FileNotFoundError(f"Baseline CSV not found: {csv_path}")

        df = pd.read_csv(csv_path, dtype={"CAN ID": str})
        time_col = _resolve_column(df, ["timestamp", "time", "ts"])
        if time_col:
            df = df.sort_values(by=time_col).reset_index(drop=True)
        n = len(df)
        # Use 70% as training split (same as eval script)
        train_df = df.iloc[: int(0.70 * n)].copy()

        engine, _profiler = _build_engine_from_df(train_df, rules_path)
        stage2 = Stage2Model()
        rng = random.Random(_SAMPLE_SEED)
        return cls(engine=engine, stage2=stage2, rng=rng)

    def run(self, frames: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluate *frames* through the full pipeline and return a result dict.

        Each frame dict should contain at minimum: ``timestamp``, ``can_id``,
        ``dlc``, and optionally ``payload`` (hex string).

        Returns a dict with keys:
        - ``total_frames``        – total input count
        - ``normal_count``        – frames whose final label is "normal"
        - ``alert_count``         – frames whose final label != "normal"
        - ``by_label``            – {label: count}
        - ``by_severity``         – {level: count}
        - ``rule_hits``           – {rule_id: count}
        - ``execution_time_ms``   – wall-clock ms
        - ``alerts``              – list of alert dicts (one per non-normal frame)
        """
        sf = StreamingFeatures()
        fusion_state = FusionState()

        alert_count = 0
        normal_count = 0
        by_label: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        rule_hits: Dict[str, int] = {}
        alert_list: List[Dict[str, Any]] = []
        ml_failures = 0

        t0 = time.perf_counter()

        for frame in frames:
            # ---- Feature extraction ----
            enriched = sf.update(frame)
            timestamp = enriched.get("timestamp") or enriched.get("Timestamp") or 0.0
            can_id = int(enriched.get("can_id", 0))

            # ---- Stage 1 ----
            rule_verdict = self._engine.evaluate(enriched)
            for hit in rule_verdict.hits:
                rule_hits[hit.rule_id] = rule_hits.get(hit.rule_id, 0) + 1

            # ---- Stage 2 sampling logic ----
            sampled = False
            stage2_class = "normal"
            stage2_prob = 0.97
            stage2_probs: Dict[str, float] = {}
            stage2_error: Optional[str] = None

            verdict = rule_verdict.verdict
            if verdict in ("VIOLATION", "SUSPECT"):
                # Always run Stage 2 for flagged frames
                try:
                    stage2_class, stage2_probs = self._stage2.predict(enriched)
                    stage2_prob = stage2_probs.get(stage2_class, 0.5)
                    sampled = True
                except Exception as exc:
                    ml_failures += 1
                    stage2_error = str(exc)
                    stage2_class, stage2_prob = "normal", 1.0
            elif verdict == "CLEAN" and self._rng.random() < _SAMPLE_RATE:
                # 10% random sampling for CLEAN frames
                try:
                    stage2_class, stage2_probs = self._stage2.predict(enriched)
                    stage2_prob = stage2_probs.get(stage2_class, 0.5)
                    sampled = True
                except Exception as exc:
                    ml_failures += 1
                    stage2_error = str(exc)
                    stage2_class, stage2_prob = "normal", 1.0

            # ---- Fusion ----
            decision = decide(
                rule_verdict=rule_verdict,
                stage2_class=stage2_class,
                stage2_prob=stage2_prob,
                can_id=can_id,
                timestamp=float(timestamp),
                state=fusion_state,
                sampled=sampled,
            )

            # ---- Severity ----
            sev_score, sev_level = severity_score(decision, rule_verdict, can_id)

            # ---- Tally ----
            label = decision.label
            by_label[label] = by_label.get(label, 0) + 1
            by_severity[sev_level] = by_severity.get(sev_level, 0) + 1

            if label.lower() == "normal":
                normal_count += 1
            else:
                rule_evidence = [hit.reason for hit in rule_verdict.hits]
                reason_parts = rule_evidence + [decision.reason]
                if sampled:
                    reason_parts.append(
                        f"Stage 2 {getattr(self._stage2, 'mode', 'unknown')} prediction: "
                        f"{stage2_class} ({stage2_prob:.3f})"
                    )
                if stage2_error:
                    reason_parts.append(
                        f"Stage 2 inference unavailable: {stage2_error}"
                    )
                shap_values = (
                    self._stage2.explain(enriched, stage2_class)
                    if sampled and getattr(self._stage2, "mode", None) == "trained"
                    else None
                )
                alert_count += 1
                alert_list.append(
                    {
                        "timestamp": float(timestamp),
                        "can_id": can_id,
                        "label": label,
                        "confidence": round(decision.confidence, 4),
                        "stage": decision.stage,
                        "severity_level": sev_level,
                        "severity_score": sev_score,
                        "rule_ids": ",".join(decision.rule_ids),
                        "reason": "; ".join(reason_parts),
                        "rule_evidence": rule_evidence,
                        "stage2_prediction": stage2_class if sampled else None,
                        "stage2_confidence": round(stage2_prob, 4) if sampled else None,
                        "stage2_mode": getattr(self._stage2, "mode", "unknown"),
                        "shap_values": shap_values,
                    }
                )

        execution_time_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "total_frames": len(frames),
            "normal_count": normal_count,
            "alert_count": alert_count,
            "by_label": by_label,
            "by_severity": by_severity,
            "rule_hits": rule_hits,
            "ml_mode": getattr(self._stage2, "mode", "unknown"),
            "ml_failures": ml_failures,
            "execution_time_ms": round(execution_time_ms, 2),
            "alerts": alert_list,
        }
