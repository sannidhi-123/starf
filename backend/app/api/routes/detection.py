"""Detection run API route.

POST /api/v1/detection/run — accepts DetectionRunRequest, executes the full
pipeline (rules → ML → fusion → severity) via DetectionService, persists
alerts, and returns a rich result payload.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.detection.schemas import DetectionRunRequest
from app.modules.detection.service import DetectionService

router = APIRouter()
_svc = DetectionService()


@router.post("/run")
async def run_detection(request: DetectionRunRequest) -> dict:
    """Run the end-to-end CAN-frame anomaly detection pipeline."""
    return await _svc.run(request)


@router.get("/runs")
async def get_recent_runs() -> dict:
    """Return historical detection runs executed during this session."""
    return {"items": _svc.get_recent_runs()}
