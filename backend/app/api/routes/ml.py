"""ML models API route.

GET /api/v1/ml/models — returns metadata and telemetry for STARF pipeline stages.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.ml.service import MLService

router = APIRouter()
_svc = MLService()


@router.get("/models")
async def list_models() -> dict:
    """Return all models in the STARF 3-stage hybrid detection architecture."""
    return {"items": _svc.get_models()}
