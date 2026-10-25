"""DetectionService: runs the full pipeline for a DetectionRunRequest."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from fastapi import HTTPException

from app.modules.alerts.service import AlertService
from app.modules.detection.schemas import DetectionRunRequest, JobStatus

# Resolve paths relative to the repo root (two levels above backend/)
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SAMPLES_DIR = _REPO_ROOT / "data" / "samples"
_RULES_YAML = _REPO_ROOT / "config" / "rules.yaml"
_BASELINE_CSV = _SAMPLES_DIR / "fixture.csv"


def _load_pipeline():
    """Lazy import so uvicorn can start even if stark isn't on sys.path yet."""
    import sys

    # Ensure src/ is importable when running uvicorn directly from backend/
    src_dir = str(_REPO_ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    from stark.pipeline.runner import DetectionPipeline

    return DetectionPipeline.from_config(
        rules_yaml=str(_RULES_YAML),
        baseline_csv=str(_BASELINE_CSV),
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
    """Read a Car-Hacking CSV and convert each row to a frame dict."""
    df = pd.read_csv(path, dtype={"CAN ID": str})
    frames: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        # Resolve CAN ID column name
        can_id_raw = (
            row.get("CAN ID")
            or row.get("can_id")
            or row.get("id")
            or "0"
        )
        ts_raw = row.get("Timestamp") or row.get("timestamp") or row.get("ts") or 0.0
        dlc_raw = row.get("DLC") or row.get("dlc") or 0

        # Build hex payload from DATA[0]…DATA[7] columns
        data_cols = [f"DATA[{i}]" for i in range(8)]
        byte_vals = []
        for col in data_cols:
            v = row.get(col)
            if v is not None and str(v).strip() not in ("", "nan"):
                try:
                    byte_vals.append(int(str(v).strip(), 16) & 0xFF)
                except ValueError:
                    try:
                        byte_vals.append(int(str(v).strip()) & 0xFF)
                    except ValueError:
                        pass
        payload = "".join(f"{b:02X}" for b in byte_vals)

        frames.append(
            {
                "timestamp": float(ts_raw),
                "can_id": str(can_id_raw),
                "dlc": int(dlc_raw),
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
                raise HTTPException(status_code=422, detail="Invalid dataset_id: path traversal not allowed.")
            csv_path = _SAMPLES_DIR / f"{ds_id}.csv"
            if not csv_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Dataset '{ds_id}' not found. Available: "
                    + ", ".join(p.stem for p in _SAMPLES_DIR.glob("*.csv")),
                )
            raw_frames = _csv_to_frames(csv_path)
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
