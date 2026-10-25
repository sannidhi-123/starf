"""Datasets API route.

GET /api/v1/datasets — returns metadata for every CSV in data/samples/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SAMPLES_DIR = _REPO_ROOT / "data" / "samples"


@router.get("")
async def list_datasets() -> dict:
    """Return id, name, and row-count for every CSV in data/samples/."""
    items = []
    if _SAMPLES_DIR.exists():
        for p in sorted(_SAMPLES_DIR.glob("*.csv")):
            try:
                df = pd.read_csv(p, nrows=0)  # header only for speed
                # Full row count
                rows = sum(1 for _ in open(p, encoding="utf-8")) - 1
            except Exception:
                rows = -1
            items.append(
                {
                    "id": p.stem,
                    "name": p.stem.replace("_", " ").title(),
                    "rows": rows,
                }
            )
    return {"items": items}
