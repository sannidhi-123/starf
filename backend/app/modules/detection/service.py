"""DetectionService: runs the full pipeline for a DetectionRunRequest."""

from __future__ import annotations

import uuid
import math
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from fastapi import HTTPException

from app.core.paths import get_repo_root, get_rules_yaml, get_samples_dir
from app.modules.alerts.service import AlertService
from app.modules.detection.schemas import DetectionRunRequest, JobStatus


def _load_pipeline():
    """Lazy import so uvicorn can start even if stark isn't on sys.path yet."""
    import sys

    # Ensure src/ is importable when running uvicorn directly from backend/
    repo_root = get_repo_root()
    src_dir = str(repo_root / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    from stark.pipeline.runner import DetectionPipeline

    rules_yaml = get_rules_yaml()
    baseline_csv = get_samples_dir() / "fixture.csv"

    return DetectionPipeline.from_config(
        rules_yaml=str(rules_yaml),
        baseline_csv=str(baseline_csv),
    )


# Module-level singleton — built on first request, reused thereafter.
_pipeline = None
_recent_runs: List[Dict[str, Any]] = []


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = _load_pipeline()
    return _pipeline


def _csv_to_frames(path: Path) -> List[Dict[str, Any]]:
    """Read supported CAN CSV rows, failing with row-specific input errors."""
    df = pd.read_csv(path, dtype={"CAN ID": str})
    frames: List[Dict[str, Any]] = []
    for index, row in df.iterrows():
        row_number = int(index) + 2
        # Resolve CAN ID column name
        id_column = next(
            (
                key
                for key in ("CAN ID", "can_id", "id", "arbitration_id")
                if key in row and pd.notna(row.get(key))
            ),
            None,
        )
        can_id_raw = row.get(id_column) if id_column else None
        ts_raw = next(
            (
                row.get(k)
                for k in ("Timestamp", "timestamp", "ts")
                if k in row and pd.notna(row.get(k))
            ),
            None,
        )
        dlc_raw = next(
            (row.get(k) for k in ("DLC", "dlc") if k in row and pd.notna(row.get(k))),
            None,
        )
        if pd.isna(can_id_raw) or ts_raw is None or dlc_raw is None:
            raise ValueError(
                f"CSV row {row_number}: timestamp, CAN ID, and DLC are required"
            )
        try:
            raw_id_text = str(can_id_raw).strip()
            is_car_hacking = str(id_column).strip().lower() == "can id"
            parsed_can_id = (
                int(raw_id_text, 16)
                if raw_id_text.lower().startswith("0x") or is_car_hacking
                else int(
                    raw_id_text,
                    16 if any(c in "abcdefABCDEF" for c in raw_id_text) else 10,
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"CSV row {row_number}: invalid CAN ID {can_id_raw!r}"
            ) from exc
        if not 0 <= parsed_can_id <= 0x1FFFFFFF:
            raise ValueError(
                f"CSV row {row_number}: CAN ID is outside the 29-bit range"
            )

        # Build hex payload from DATA[0]…DATA[7] columns
        data_cols = [f"DATA[{i}]" for i in range(8)]
        byte_vals = []
        for col in data_cols:
            v = row.get(col)
            if v is not None and str(v).strip() not in ("", "nan"):
                try:
                    byte_val = int(str(v).strip(), 16)
                except ValueError as exc:
                    raise ValueError(
                        f"CSV row {row_number}: invalid payload byte {v!r}"
                    ) from exc
                if not 0 <= byte_val <= 255:
                    raise ValueError(
                        f"CSV row {row_number}: payload byte out of range: {v!r}"
                    )
                byte_vals.append(byte_val)
        payload = "".join(f"{b:02X}" for b in byte_vals)

        try:
            ts_val = float(ts_raw)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"CSV row {row_number}: invalid timestamp {ts_raw!r}"
            ) from exc
        if not math.isfinite(ts_val) or ts_val < 0:
            raise ValueError(
                f"CSV row {row_number}: timestamp must be finite and non-negative"
            )

        try:
            dlc_val = int(dlc_raw)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"CSV row {row_number}: invalid DLC {dlc_raw!r}") from exc
        if not 0 <= dlc_val <= 8:
            raise ValueError(f"CSV row {row_number}: DLC must be between 0 and 8")
        if byte_vals and len(byte_vals) != dlc_val:
            raise ValueError(
                f"CSV row {row_number}: payload has {len(byte_vals)} bytes but DLC is {dlc_val}"
            )

        frames.append(
            {
                "timestamp": ts_val,
                "can_id": parsed_can_id,
                "dlc": dlc_val,
                "payload": payload,
            }
        )
    return frames


class DetectionService:
    """Application service that wires DetectionRunRequest → pipeline → alerts."""

    _alert_svc = AlertService()

    async def run(self, request: DetectionRunRequest) -> Dict[str, Any]:
        """Execute the detection pipeline and persist alerts.

        Args:
            request: Validated DetectionRunRequest (frames or dataset_id).

        Returns:
            Dict with job_id, status, total_frames, alert_count, by_label,
            by_severity, rule_hits, execution_time_ms, run_id, summary.

        Raises:
            HTTPException 404: Unknown dataset_id.
            HTTPException 422: Path traversal attempt.
        """
        run_id = str(uuid.uuid4())

        # ---- Resolve frames ----
        if request.dataset_id:
            ds_id = request.dataset_id
            # Guard against path traversal
            if ".." in ds_id or "/" in ds_id or "\\" in ds_id:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid dataset_id: path traversal not allowed.",
                )
            samples_dir = get_samples_dir()
            csv_path = samples_dir / f"{ds_id}.csv"
            if not csv_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Dataset '{ds_id}' not found. Available: "
                    + ", ".join(p.stem for p in samples_dir.glob("*.csv")),
                )
            try:
                raw_frames = _csv_to_frames(csv_path)
            except (ValueError, pd.errors.ParserError) as exc:
                raise HTTPException(
                    status_code=422, detail=f"Invalid CAN dataset: {exc}"
                ) from exc
        else:
            # Convert CANFrameInput objects to plain dicts
            raw_frames = [
                {
                    "timestamp": f.timestamp,
                    "can_id": f.can_id,
                    "dlc": f.dlc,
                    "payload": f.payload,
                }
                for f in (request.frames or [])
            ]

        if not raw_frames:
            raise HTTPException(status_code=422, detail="No frames to evaluate.")

        # ---- Run pipeline ----
        pipeline = _get_pipeline()
        result = pipeline.run(raw_frames)

        # ---- Persist alerts ----
        alerts_list = result["alerts"]
        if alerts_list:
            await self._alert_svc.add_many(run_id, alerts_list)

        # ---- Build summary ----
        summary = {
            "total": result["alert_count"],
            "by_label": result["by_label"],
            "by_severity": result["by_severity"],
        }

        # Format alerts preview with can_id_hex
        formatted_alerts = []
        for a in alerts_list[:100]:
            cid = a.get("can_id", 0)
            formatted_alerts.append(
                {
                    "can_id": cid,
                    "can_id_hex": f"0x{cid:04X}" if isinstance(cid, int) else str(cid),
                    "timestamp": a.get("timestamp", 0.0),
                    "label": a.get("label", "normal"),
                    "confidence": a.get("confidence", 0.0),
                    "stage": a.get("stage", "stage1"),
                    "severity_level": a.get("severity_level", "LOW"),
                    "severity_score": a.get("severity_score", 0),
                    "rule_ids": a.get("rule_ids", ""),
                    "reason": a.get("reason", ""),
                    "rule_evidence": a.get("rule_evidence", []),
                    "stage2_prediction": a.get("stage2_prediction"),
                    "stage2_confidence": a.get("stage2_confidence"),
                    "stage2_mode": a.get(
                        "stage2_mode", result.get("ml_mode", "unknown")
                    ),
                    "shap_values": a.get("shap_values"),
                    "details": {
                        key: a.get(key)
                        for key in (
                            "rule_evidence",
                            "stage2_prediction",
                            "stage2_confidence",
                            "stage2_mode",
                            "shap_values",
                        )
                        if a.get(key) is not None
                    },
                }
            )

        resp = {
            "job_id": run_id,
            "run_id": run_id,
            "dataset_id": request.dataset_id,
            "status": JobStatus.COMPLETED,
            "total_frames": result["total_frames"],
            "normal_count": result["normal_count"],
            "alert_count": result["alert_count"],
            "suspicious_count": result["alert_count"],
            "matches": result["alert_count"],
            "by_label": result["by_label"],
            "by_severity": result["by_severity"],
            "rule_hits": result["rule_hits"],
            "ml_mode": result.get("ml_mode", "unknown"),
            "ml_failures": result.get("ml_failures", 0),
            "execution_time_ms": result["execution_time_ms"],
            "summary": summary,
            "alerts": formatted_alerts,
        }

        # Store in circular recent runs buffer
        _recent_runs.insert(0, resp)
        if len(_recent_runs) > 50:
            _recent_runs.pop()

        return resp

    def get_recent_runs(self) -> List[Dict[str, Any]]:
        """Return list of recent detection runs."""
        return _recent_runs
